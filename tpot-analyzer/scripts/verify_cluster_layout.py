"""
Human-friendly verifier for cluster layout continuity and headroom calculations.

Checks:
- Budget headroom: base cut is below max budget to leave room for expand.
- Procrustes alignment: alignment reduces RMS error between two layouts.

Usage: python scripts/verify_cluster_layout.py
"""

import math
import random
import sys
from typing import List, Tuple


def compute_base_cut(budget: int) -> int:
    capped = max(5, min(500, budget))
    headroom_cut = round(capped * 0.45)
    return max(5, min(capped, headroom_cut if capped - 1 < 8 else min(headroom_cut, capped - 1)))


def generate_layout(n: int) -> List[Tuple[float, float]]:
    points = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        r = 1.0 + 0.1 * math.sin(i)
        points.append((r * math.cos(angle), r * math.sin(angle)))
    return points


def transform_layout(points: List[Tuple[float, float]], angle: float, scale: float) -> List[Tuple[float, float]]:
    rot = [
        [math.cos(angle), -math.sin(angle)],
        [math.sin(angle), math.cos(angle)],
    ]
    out = []
    for x, y in points:
        nx = scale * (x * rot[0][0] + y * rot[0][1])
        ny = scale * (x * rot[1][0] + y * rot[1][1])
        # add tiny jitter
        nx += random.uniform(-0.02, 0.02)
        ny += random.uniform(-0.02, 0.02)
        out.append((nx, ny))
    return out


def center(points):
    n = len(points)
    if n == 0:
        return [], (0.0, 0.0), 1.0
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    centered = [(p[0] - mean_x, p[1] - mean_y) for p in points]
    scale = math.sqrt(sum(px * px + py * py for px, py in centered)) or 1.0
    return [(px / scale, py / scale) for px, py in centered], (mean_x, mean_y), scale


def procrustes_align(A: List[Tuple[float, float]], B: List[Tuple[float, float]]):
    if len(A) != len(B) or len(A) < 2:
        return B, {"aligned": False, "overlap": len(A), "rms_before": None, "rms_after": None}

    Ac, mean_a, scale_a = center(A)
    Bc, mean_b, scale_b = center(B)

    m00 = sum(bx * ax for (bx, by), (ax, ay) in zip(Bc, Ac))
    m01 = sum(bx * ay for (bx, by), (ax, ay) in zip(Bc, Ac))
    m10 = sum(by * ax for (bx, by), (ax, ay) in zip(Bc, Ac))
    m11 = sum(by * ay for (bx, by), (ax, ay) in zip(Bc, Ac))

    T = m00 + m11
    S = math.sqrt((m00 - m11) ** 2 + (m01 + m10) ** 2)
    trace = math.sqrt(max(T + S, 0) / 2) + math.sqrt(max(T - S, 0) / 2)
    scale = trace / (scale_b or 1)

    denom = math.hypot(m00 + m11, m01 - m10) or 1
    r00 = (m00 + m11) / denom
    r01 = (m01 - m10) / denom
    r10 = (m10 - m01) / denom
    r11 = (m00 + m11) / denom

    aligned = []
    for (bx, by) in B:
        x = (bx - mean_b[0]) / (scale_b or 1)
        y = (by - mean_b[1]) / (scale_b or 1)
        rx = x * r00 + y * r01
        ry = x * r10 + y * r11
        aligned.append((rx * scale + mean_a[0], ry * scale + mean_a[1]))

    def rms(points_a, points_b):
        return math.sqrt(sum((ax - bx) ** 2 + (ay - by) ** 2 for (ax, ay), (bx, by) in zip(points_a, points_b)) / len(points_a))

    rms_before = rms(A, B)
    rms_after = rms(A, aligned)
    return aligned, {"aligned": True, "overlap": len(A), "rms_before": rms_before, "rms_after": rms_after, "scale": scale}


def status(ok: bool, message: str):
    prefix = "✓" if ok else "✗"
    print(f"{prefix} {message}")


def main():
    budgets = [10, 25, 50]
    print("Budget headroom checks:")
    for b in budgets:
        base = compute_base_cut(b)
        ok = base < b
        status(ok, f"budget={b} -> base_cut={base} (headroom={b - base})")

    print("\nLayout continuity checks:")
    pts = generate_layout(25)
    transformed = transform_layout(pts, angle=math.pi / 3, scale=1.2)
    aligned, stats = procrustes_align(pts, transformed)
    if not stats["aligned"]:
        status(False, "procrustes alignment not run (insufficient overlap)")
    else:
        status(stats["rms_after"] < stats["rms_before"], f"procrustes improves RMS {stats['rms_before']:.4f} -> {stats['rms_after']:.4f} (scale={stats['scale']:.3f})")

    print("\nMetrics:")
    print(f"- overlap: {stats.get('overlap')}")
    print(f"- rms_before: {stats.get('rms_before')}")
    print(f"- rms_after: {stats.get('rms_after')}")

    print("\nNext steps:")
    print("1) Run the UI and collapse/expand clusters; confirm positions glide instead of teleporting.")
    print("2) If RMS_after is not lower, inspect PCA alignment and ensure overlap>=2.")
    print("3) Adjust base cut formula if headroom is too small/large for your hardware.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
