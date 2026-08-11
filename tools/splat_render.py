#!/usr/bin/env python3
"""
splat_render.py - renders a 3D Gaussian splat to an animated turntable.

Why this exists: GitHub READMEs cannot run JavaScript. Images are served through
a proxy and rendered as plain <img> documents, so WebGL - and therefore every
normal Gaussian-splat viewer - is unavailable. The only way to put a splat on a
profile page is to rasterise it ourselves, ahead of time, and ship the frames.

So this is a complete EWA splatting rasteriser in numpy. No GPU, no WebGL, no
native extensions, which also means it reproduces unchanged inside a GitHub
Action runner.

The pipeline per frame is the standard one:

  1. transform gaussian centres into camera space and cull
  2. project to screen, and push the 3D covariance through the Jacobian of the
     projection to get a 2D covariance  (Sigma' = J W Sigma W^T J^T)
  3. invert that to a conic, giving each gaussian an elliptical footprint
  4. sort front-to-back and alpha-composite with a running transmittance

    python tools/splat_render.py splat.ply --out ../assets/statue
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

import numpy as np

SH_C0 = 0.28209479177387814

# Screen-space low-pass. Without it, gaussians that project smaller than a pixel
# alias into flickering speckle as the camera turns - very visible in a loop.
BLUR_2D = 0.3

# Below this the gaussian cannot change the pixel enough to be worth compositing.
MIN_ALPHA = 1.0 / 255.0


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_ply(path: pathlib.Path) -> dict:
    raw = path.read_bytes()
    marker = b"end_header\n"
    end = raw.index(marker) + len(marker)
    header = raw[:end].decode("ascii")

    if "binary_little_endian" not in header:
        raise SystemExit("only binary_little_endian PLY files are supported")

    props = [l.split()[-1] for l in header.splitlines() if l.startswith("property")]
    count = int(
        next(l for l in header.splitlines() if l.startswith("element vertex")).split()[-1]
    )
    data = np.frombuffer(raw[end:], dtype="<f4").reshape(count, len(props))
    idx = {n: i for i, n in enumerate(props)}

    def col(*names):
        return data[:, [idx[n] for n in names]].astype(np.float32)

    xyz = col("x", "y", "z")
    rgb = 0.5 + SH_C0 * col("f_dc_0", "f_dc_1", "f_dc_2")
    opacity = 1.0 / (1.0 + np.exp(-data[:, idx["opacity"]]))
    scale = np.exp(col("scale_0", "scale_1", "scale_2"))
    rot = col("rot_0", "rot_1", "rot_2", "rot_3")
    rot /= np.linalg.norm(rot, axis=1, keepdims=True) + 1e-9

    return {
        "xyz": xyz.astype(np.float64),
        "rgb": np.clip(rgb, 0, 1).astype(np.float64),
        "opacity": opacity.astype(np.float64),
        "scale": scale.astype(np.float64),
        "rot": rot.astype(np.float64),
        "count": count,
    }


def covariance3d(scale: np.ndarray, rot: np.ndarray) -> np.ndarray:
    """Sigma = R S S^T R^T, built for every gaussian at once."""
    w, x, y, z = rot[:, 0], rot[:, 1], rot[:, 2], rot[:, 3]
    R = np.empty((len(rot), 3, 3))
    R[:, 0, 0] = 1 - 2 * (y * y + z * z)
    R[:, 0, 1] = 2 * (x * y - w * z)
    R[:, 0, 2] = 2 * (x * z + w * y)
    R[:, 1, 0] = 2 * (x * y + w * z)
    R[:, 1, 1] = 1 - 2 * (x * x + z * z)
    R[:, 1, 2] = 2 * (y * z - w * x)
    R[:, 2, 0] = 2 * (x * z - w * y)
    R[:, 2, 1] = 2 * (y * z + w * x)
    R[:, 2, 2] = 1 - 2 * (x * x + y * y)

    M = R * scale[:, None, :]          # R @ diag(scale)
    return M @ np.transpose(M, (0, 2, 1))


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


def look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    W = np.eye(4)
    W[0, :3], W[1, :3], W[2, :3] = s, u, -f
    W[:3, 3] = -W[:3, :3] @ eye
    return W


# ---------------------------------------------------------------------------
# Rasteriser
# ---------------------------------------------------------------------------


def render_frame(g: dict, cov3d: np.ndarray, W: np.ndarray,
                 width: int, height: int, fov_y: float) -> tuple[np.ndarray, np.ndarray]:
    """Returns (premultiplied colour, transmittance).

    Handing back transmittance rather than a composited image lets the caller
    choose between a solid background and an alpha channel. Alpha is what we
    actually want on GitHub: one transparent file sits correctly on both the
    light and the dark theme, instead of needing a variant for each.
    """
    H, Wd = height, width
    R, t = W[:3, :3], W[:3, 3]

    cam = g["xyz"] @ R.T + t
    z = -cam[:, 2]                       # looking down -Z

    near = 0.05
    vis = z > near
    if not vis.any():
        return np.zeros((H, Wd, 3)), np.ones((H, Wd))

    # Vertical field of view, so the framing is stable if the width changes.
    focal = 0.5 * H / np.tan(0.5 * fov_y)
    cam_v, z_v = cam[vis], z[vis]

    # Perspective divide, then to pixels.
    u = focal * cam_v[:, 0] / z_v + Wd * 0.5
    v = -focal * cam_v[:, 1] / z_v + H * 0.5

    # Jacobian of the projection, evaluated per gaussian.
    J = np.zeros((len(cam_v), 2, 3))
    J[:, 0, 0] = focal / z_v
    J[:, 0, 2] = focal * cam_v[:, 0] / (z_v * z_v)
    J[:, 1, 1] = -focal / z_v
    J[:, 1, 2] = -focal * cam_v[:, 1] / (z_v * z_v)

    T = J @ R                            # world -> screen linearisation
    cov2d = T @ cov3d[vis] @ np.transpose(T, (0, 2, 1))
    cov2d[:, 0, 0] += BLUR_2D
    cov2d[:, 1, 1] += BLUR_2D

    a, b, c = cov2d[:, 0, 0], cov2d[:, 0, 1], cov2d[:, 1, 1]
    det = a * c - b * b
    good = det > 1e-8
    if not good.any():
        return np.zeros((H, Wd, 3)), np.ones((H, Wd))

    # Conic = inverse 2D covariance, used directly in the exponent.
    inv = 1.0 / det
    con_a, con_b, con_c = c * inv, -b * inv, a * inv

    # 3-sigma extent of the ellipse, via the larger eigenvalue.
    mid = 0.5 * (a + c)
    disc = np.sqrt(np.maximum(mid * mid - det, 0))
    radius = np.ceil(3.0 * np.sqrt(np.maximum(mid + disc, 1e-6))).astype(int)

    colour, alpha0 = g["rgb"][vis], g["opacity"][vis]

    on_screen = (
        good
        & (u + radius >= 0) & (u - radius < Wd)
        & (v + radius >= 0) & (v - radius < H)
        & (radius >= 1) & (radius <= max(width, height))   # drop degenerate giants
        & (alpha0 > 0.02)
    )

    order = np.argsort(z_v[on_screen])          # front to back
    ui, vi = u[on_screen][order], v[on_screen][order]
    rad = radius[on_screen][order]
    ca, cb, cc = (con_a[on_screen][order], con_b[on_screen][order],
                  con_c[on_screen][order])
    col = colour[on_screen][order]
    al = alpha0[on_screen][order]

    img = np.zeros((H, Wd, 3))
    trans = np.ones((H, Wd))                    # remaining light through

    for i in range(len(ui)):
        r = rad[i]
        x0, x1 = max(0, int(ui[i]) - r), min(Wd, int(ui[i]) + r + 1)
        y0, y1 = max(0, int(vi[i]) - r), min(H, int(vi[i]) + r + 1)
        if x0 >= x1 or y0 >= y1:
            continue

        Tp = trans[y0:y1, x0:x1]
        if Tp.max() < 0.005:                    # fully occluded already
            continue

        dx = np.arange(x0, x1) - ui[i]
        dy = np.arange(y0, y1) - vi[i]
        DX = dx[None, :]
        DY = dy[:, None]
        power = -0.5 * (ca[i] * DX * DX + cc[i] * DY * DY) - cb[i] * DX * DY

        a_i = al[i] * np.exp(np.minimum(power, 0.0))
        np.clip(a_i, 0, 0.99, out=a_i)
        a_i[a_i < MIN_ALPHA] = 0.0

        contrib = Tp * a_i
        img[y0:y1, x0:x1] += contrib[:, :, None] * col[i]
        Tp *= 1.0 - a_i

    return img, trans


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def auto_frame(g: dict, up_axis: int) -> tuple[np.ndarray, float, float]:
    """Centre the subject and measure it, ignoring low-opacity floaters.

    Splats reconstructed from photographs are always surrounded by faint junk,
    so a raw bounding box frames the junk and leaves the subject tiny. Percentile
    extents are used instead of min/max for the same reason.

    Vertical centring is deliberately the midpoint of the figure rather than the
    median point: for a standing person, most gaussians sit in the torso, so the
    median puts the head out of frame.
    """
    solid = g["opacity"] > 0.25
    pts = g["xyz"][solid]

    lo, hi = np.percentile(pts, [1.0, 99.0], axis=0)
    # Midpoint of the extents on every axis, not the median. The median tracks
    # where the mass is - the torso - which both drops the head out of frame and
    # puts the turntable axis off-centre, so the subject visibly swings from
    # side to side through the loop.
    centre = 0.5 * (lo + hi)

    half_height = float(0.5 * (hi[up_axis] - lo[up_axis]))
    flat = [k for k in range(3) if k != up_axis]
    half_width = float(0.5 * max(hi[k] - lo[k] for k in flat))
    return centre, half_height, half_width


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ply", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, required=True,
                    help="output prefix; frames go to <out>_frames/")
    ap.add_argument("--width", type=int, default=380)
    ap.add_argument("--height", type=int, default=560)
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--fov", type=float, default=30.0)
    ap.add_argument("--elevation", type=float, default=6.0,
                    help="degrees above the horizon")
    ap.add_argument("--margin", type=float, default=1.20,
                    help="framing slack; 1.0 touches the top and bottom edges")
    ap.add_argument("--up", default="z", choices=["x", "y", "z"],
                    help="which world axis is vertical (Nerfstudio writes z)")
    ap.add_argument("--bg", default=None,
                    help="solid background hex; omit for a transparent PNG, "
                         "which is what lets one file work on both GitHub themes")
    ap.add_argument("--start", type=float, default=0.0, help="start azimuth")
    args = ap.parse_args()

    print(f"loading {args.ply.name} ...")
    g = load_ply(args.ply)
    print(f"  {g['count']:,} gaussians")

    up_axis = "xyz".index(args.up)
    centre, half_h, half_w = auto_frame(g, up_axis)
    g["xyz"] -= centre

    # Pull the camera back far enough that the whole figure fits vertically,
    # and far enough that its width fits too once the aspect ratio is applied.
    fov_y = np.radians(args.fov)
    fov_x = 2 * np.arctan(np.tan(fov_y / 2) * args.width / args.height)
    dist = args.margin * max(half_h / np.tan(fov_y / 2),
                             half_w / np.tan(fov_x / 2))
    print(f"  subject {half_h * 2:.3f} tall, {half_w * 2:.3f} wide "
          f"-> camera at {dist:.3f}")

    print("building covariances ...")
    cov3d = covariance3d(g["scale"], g["rot"])

    up = np.zeros(3)
    up[up_axis] = 1.0
    bg = (np.array([int(args.bg[i:i + 2], 16) / 255 for i in (1, 3, 5)])
          if args.bg else None)

    frame_dir = args.out.parent / f"{args.out.name}_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for old in frame_dir.glob("*.png"):
        old.unlink()

    from PIL import Image

    elev = np.radians(args.elevation)
    ai, bi = [k for k in range(3) if k != up_axis]
    t0 = time.time()

    for i in range(args.frames):
        az = np.radians(args.start) + 2 * np.pi * i / args.frames
        # Orbit in the plane perpendicular to the up axis.
        eye = np.zeros(3)
        eye[ai] = np.cos(elev) * dist * np.cos(az)
        eye[bi] = np.cos(elev) * dist * np.sin(az)
        eye[up_axis] = np.sin(elev) * dist

        colour, trans = render_frame(
            g, cov3d, look_at(eye, np.zeros(3), up),
            args.width, args.height, fov_y,
        )

        if bg is None:
            alpha = 1.0 - trans
            # Un-premultiply, guarding the transparent pixels where the
            # division is meaningless.
            safe = np.maximum(alpha, 1e-6)[:, :, None]
            rgb = np.where(alpha[:, :, None] > 1e-4, colour / safe, 0.0)
            out = np.dstack([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)])
        else:
            out = np.clip(colour + trans[:, :, None] * bg, 0, 1)

        Image.fromarray((out * 255).astype(np.uint8)).save(frame_dir / f"{i:04d}.png")

        done = i + 1
        rate = done / (time.time() - t0)
        sys.stdout.write(
            f"\r  frame {done}/{args.frames}  ({rate:.1f}/s, "
            f"{(args.frames - done) / max(rate, 1e-6):.0f}s left)   "
        )
        sys.stdout.flush()

    print(f"\ndone in {time.time() - t0:.1f}s -> {frame_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
