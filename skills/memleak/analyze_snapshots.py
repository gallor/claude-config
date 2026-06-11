#!/usr/bin/env python3
"""Analyze tracemalloc snapshots to identify memory leak sources.

Usage:
    analyze_snapshots.py <snapshot1.pkl> <snapshot2.pkl> [snapshot3.pkl ...]

Compares consecutive snapshots and reports:
  - Top growers by size and count
  - Full tracebacks for the biggest leak sources
  - Growth trend across all snapshots (plateau detection)

Supports both tracemalloc pickle snapshots (.pkl) and memray bin files (.bin).
"""

import pickle
import sys
from pathlib import Path


def load_snapshot(path: str):
    """Load a tracemalloc snapshot from a pickle file."""
    with open(path, "rb") as f:
        return pickle.load(f)


def print_header(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def diff_pair(snap_a, snap_b, label: str):
    """Diff two tracemalloc snapshots."""
    print_header(f"Diff: {label}")

    by_size = snap_b.compare_to(snap_a, "lineno")
    growers = [s for s in by_size if s.size_diff > 0]

    if not growers:
        print("  No growth detected.")
        return

    print(f"\n  Top 15 by size growth:")
    print(f"  {'Location':<80} {'Size':>10} {'Count':>8}")
    print(f"  {'-'*80} {'-'*10} {'-'*8}")
    for s in growers[:15]:
        loc = f"{Path(s.traceback[0].filename).name}:{s.traceback[0].lineno}" if s.traceback else "?"
        print(f"  {loc:<80} {'+' + format_size(s.size_diff):>10} {'+' + str(s.count_diff):>8}")

    print(f"\n  Top 10 by count growth:")
    by_count = sorted(growers, key=lambda s: -s.count_diff)
    for s in by_count[:10]:
        loc = f"{Path(s.traceback[0].filename).name}:{s.traceback[0].lineno}" if s.traceback else "?"
        avg = s.size // s.count if s.count else 0
        print(f"  {loc:<60} +{s.count_diff:>8} objects  avg={avg}B")

    # Full tracebacks for big growers
    by_tb = snap_b.compare_to(snap_a, "traceback")
    big = [s for s in by_tb if s.size_diff > 50_000]
    if big:
        print(f"\n  Full tracebacks (top {min(5, len(big))} by size, >50KB):")
        for s in big[:5]:
            print(f"\n  +{format_size(s.size_diff)}, +{s.count_diff} objects:")
            for line in s.traceback.format():
                print(f"    {line}")


def trend_analysis(snaps, paths):
    """Track specific allocators across all snapshots to detect plateau vs linear growth."""
    if len(snaps) < 3:
        return

    print_header("Growth Trend Analysis")

    # Find the top growers between first and last snapshot
    top = snaps[-1].compare_to(snaps[0], "lineno")
    growers = [s for s in top if s.size_diff > 10_000][:10]

    if not growers:
        print("  No significant growth between first and last snapshot.")
        return

    # For each top grower, track its absolute count across all snapshots
    for g in growers:
        key = f"{Path(g.traceback[0].filename).name}:{g.traceback[0].lineno}" if g.traceback else "?"
        counts = []
        sizes = []
        for snap in snaps:
            found = False
            for s in snap.statistics("lineno"):
                if s.traceback and g.traceback and s.traceback[0] == g.traceback[0]:
                    counts.append(s.count)
                    sizes.append(s.size)
                    found = True
                    break
            if not found:
                counts.append(0)
                sizes.append(0)

        # Determine trend
        if len(counts) >= 3:
            diffs = [counts[i+1] - counts[i] for i in range(len(counts)-1)]
            avg_diff = sum(diffs) / len(diffs)
            last_diff = diffs[-1]

            if avg_diff > 0 and last_diff < avg_diff * 0.3:
                trend = "PLATEAU"
            elif avg_diff > 0:
                trend = "GROWING"
            else:
                trend = "stable"
        else:
            trend = "?"

        print(f"\n  {key}  [{trend}]")
        for i, (c, s) in enumerate(zip(counts, sizes)):
            label = Path(paths[i]).stem
            print(f"    {label}: count={c:>8}  size={format_size(s):>10}")


def format_size(nbytes: int) -> str:
    """Human-readable size."""
    if abs(nbytes) < 1024:
        return f"{nbytes}B"
    elif abs(nbytes) < 1024 * 1024:
        return f"{nbytes / 1024:.1f}KB"
    else:
        return f"{nbytes / 1024 / 1024:.1f}MB"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    paths = sys.argv[1:]

    # Check for memray .bin files
    if any(p.endswith(".bin") for p in paths):
        print("memray .bin files detected. Use `memray flamegraph` or `memray stats` instead:")
        print(f"  memray flamegraph {paths[-1]} -o /tmp/flamegraph.html")
        print(f"  memray stats {paths[-1]}")
        if len(paths) >= 2:
            print(f"\nFor temporal comparison, run memray on each file separately")
            print(f"and compare the `memray stats` output.")
        sys.exit(0)

    print(f"Loading {len(paths)} tracemalloc snapshots...")
    snaps = []
    for p in paths:
        snaps.append(load_snapshot(p))
        print(f"  {Path(p).name}: loaded")

    # Diff consecutive pairs
    for i in range(len(snaps) - 1):
        label = f"{Path(paths[i]).name} -> {Path(paths[i+1]).name}"
        diff_pair(snaps[i], snaps[i + 1], label)

    # If 3+ snapshots, also diff first vs last and do trend analysis
    if len(snaps) >= 3:
        diff_pair(snaps[0], snaps[-1], f"{Path(paths[0]).name} -> {Path(paths[-1]).name} (full span)")
        trend_analysis(snaps, paths)

    # Summary
    print_header("Summary")
    total_minutes = (len(snaps) - 1) * 5  # assuming 5-min intervals
    first_last = snaps[-1].compare_to(snaps[0], "lineno")
    total_growth = sum(s.size_diff for s in first_last if s.size_diff > 0)
    print(f"  Snapshots: {len(snaps)}")
    print(f"  Estimated span: ~{total_minutes} minutes (assuming 5-min intervals)")
    print(f"  Total allocation growth: {format_size(total_growth)}")
    if total_minutes > 0:
        rate = total_growth / total_minutes
        print(f"  Growth rate: ~{format_size(int(rate))}/min = ~{format_size(int(rate * 60 * 24))}/day")


if __name__ == "__main__":
    main()
