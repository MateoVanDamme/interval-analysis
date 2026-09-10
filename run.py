"""Analyze a Strava GPX export and rebuild the site.

    python run.py data/3_x_5min.gpx
    python run.py data/other.gpx --min-work 60 --cadence-factor 1 --no-map

Writes, in the repo root (served by GitHub Pages):
    index.html, data.js   the three.js 3D viewer (uses viewer/style.css and viewer/app.js)
    charts/*.png          overview, per-rep pace, rep summary, pace histogram, route
    data/points.csv       per-second track with pace, cadence and phase label
    data/intervals.csv    detected work intervals
"""
from __future__ import annotations

import argparse
from pathlib import Path

import charts
from intervals import analyze, fmt_pace, recoveries, summarize
from viewer import build_viewer

HERE = Path(__file__).parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gpx", type=Path, help="GPX file exported from Strava")
    ap.add_argument("--min-work", type=float, default=120, help="minimum rep duration in seconds (default 120)")
    ap.add_argument("--max-gap", type=float, default=20, help="bridge dips shorter than this many seconds (default 20)")
    ap.add_argument("--threshold", type=float, help="speed threshold in m/s (default: automatic two-means split)")
    ap.add_argument("--cadence-factor", type=float, default=2.0,
                    help="GPX cadence to steps/min factor (Garmin per-leg: 2, default; already steps/min: 1)")
    ap.add_argument("--no-map", action="store_true", help="skip the OpenStreetMap ground texture")
    args = ap.parse_args()

    df, intervals, name = analyze(args.gpx, cadence_factor=args.cadence_factor,
                                  min_work_s=args.min_work, max_gap_s=args.max_gap, threshold=args.threshold)

    total_km = df.dist_m.iloc[-1] / 1000
    thr = intervals.attrs["threshold"]
    print(f"{name}: {total_km:.2f} km in {fmt_pace(df.t.iloc[-1] / 60)}, avg {fmt_pace(df.t.iloc[-1] / 60 / total_km)} /km")
    print(f"threshold {thr:.2f} m/s ({fmt_pace(1000 / thr / 60)} /km), {len(intervals)} work intervals")
    if len(intervals):
        print(summarize(intervals).to_string())
        if len(intervals) > 1:
            print(recoveries(df, intervals).to_string())
    else:
        print("no intervals found; try --min-work or --threshold, or this was a steady run")

    cols = ["time", "t", "lat", "lon", "ele", "dist_m", "speed", "pace_min_km", "cadence_spm", "hr", "phase"]
    df[cols].to_csv(HERE / "data" / "points.csv", index=False)
    intervals.to_csv(HERE / "data" / "intervals.csv")
    charts.save_all(df, intervals, name, HERE / "charts")
    build_viewer(df, intervals, name, HERE, with_map=not args.no_map)


if __name__ == "__main__":
    main()
