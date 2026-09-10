"""GPX parsing, pace computation and automatic interval detection.

Standard library plus pandas and numpy only. Used by run.py and the notebook.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

NS = {
    "g": "http://www.topografix.com/GPX/1/1",
    "tpx": "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
}


def fmt_pace(minutes: float) -> str:
    """Minutes as m:ss, '-' for missing values."""
    if not np.isfinite(minutes) or minutes < 0:
        return "-"
    m, s = divmod(round(minutes * 60), 60)
    return f"{int(m)}:{int(s):02d}"


def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return slug or "activity"


def read_gpx(path: str | Path) -> tuple[pd.DataFrame, str]:
    """Return (track points, activity name). Points carry time, lat, lon, ele, cadence, hr, t."""
    path = Path(path)
    root = ET.parse(path).getroot()
    name = root.findtext(".//g:name", namespaces=NS) or path.stem
    rows = []
    for pt in root.iter(f"{{{NS['g']}}}trkpt"):
        cad = pt.find(".//tpx:cad", NS)
        hr = pt.find(".//tpx:hr", NS)
        rows.append({
            "time": pd.Timestamp(pt.findtext("g:time", namespaces=NS)),
            "lat": float(pt.get("lat")),
            "lon": float(pt.get("lon")),
            "ele": float(pt.findtext("g:ele", default="nan", namespaces=NS)),
            "cadence": float(cad.text) if cad is not None else np.nan,
            "hr": float(hr.text) if hr is not None else np.nan,
        })
    if not rows:
        raise ValueError(f"{path} contains no track points")
    df = pd.DataFrame(rows)
    df["t"] = (df["time"] - df["time"].iloc[0]).dt.total_seconds()
    return df, name


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def add_pace(df: pd.DataFrame, smooth_s: int = 15, cadence_factor: float = 2.0) -> pd.DataFrame:
    """Add dist_m, speed_raw, speed (smoothed m/s), pace_min_km and cadence_spm columns.

    cadence_factor: Garmin writes strides per leg, so 2 gives steps per minute.
    Use 1 for devices that already export steps per minute.
    """
    df = df.copy()
    step_m = np.r_[0.0, haversine_m(df.lat.values[:-1], df.lon.values[:-1], df.lat.values[1:], df.lon.values[1:])]
    step_s = np.r_[1.0, np.diff(df["t"].values)]
    step_s[step_s <= 0] = 1.0
    df["dist_m"] = np.cumsum(step_m)
    df["speed_raw"] = step_m / step_s
    tindex = pd.to_timedelta(df["t"], unit="s")
    df["speed"] = pd.Series(df["speed_raw"].values, index=tindex).rolling(f"{smooth_s}s", center=True).mean().values
    with np.errstate(divide="ignore"):
        df["pace_min_km"] = 1000 / df["speed"] / 60
    df["cadence_spm"] = df["cadence"] * cadence_factor
    return df


def two_means_threshold(x: np.ndarray, iters: int = 50) -> float:
    """Split a bimodal sample into two clusters; return the midpoint between their means."""
    x = x[np.isfinite(x)]
    lo, hi = np.percentile(x, 20), np.percentile(x, 90)
    for _ in range(iters):
        thr = (lo + hi) / 2
        below, above = x[x < thr], x[x >= thr]
        if not len(below) or not len(above):
            break
        lo, hi = below.mean(), above.mean()
    return (lo + hi) / 2


def detect_intervals(df: pd.DataFrame, min_work_s: float = 120, max_gap_s: float = 20,
                     threshold: float | None = None) -> pd.DataFrame:
    """Find work intervals: stretches faster than the threshold lasting at least min_work_s.

    Dips shorter than max_gap_s inside a stretch are bridged. The threshold defaults to a
    two-means split of the smoothed speed. Result rows are named 'Rep 1', 'Rep 2', ...
    and the speed threshold is stored in .attrs['threshold'].
    """
    thr = two_means_threshold(df["speed"].values) if threshold is None else threshold
    fast = (df["speed"] >= thr).values
    t = df["t"].values

    edges = np.flatnonzero(np.diff(np.r_[0, fast.astype(int), 0]))
    runs = [(edges[i], edges[i + 1] - 1) for i in range(0, len(edges), 2)]

    merged: list[tuple[int, int]] = []
    for s, e in runs:
        if merged and t[s] - t[merged[-1][1]] <= max_gap_s:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))

    rows = []
    for s, e in merged:
        dur = t[e] - t[s]
        if dur < min_work_s:
            continue
        seg = df.iloc[s:e + 1]
        dist = seg.dist_m.iloc[-1] - seg.dist_m.iloc[0]
        rows.append({
            "start_idx": s, "end_idx": e,
            "start_s": t[s], "end_s": t[e], "duration_s": dur,
            "distance_m": dist,
            "avg_speed": dist / dur if dur else np.nan,
            "avg_pace_min_km": dur / 60 / (dist / 1000) if dist else np.nan,
            "avg_cadence_spm": seg.cadence_spm.mean(),
            "elev_gain_m": np.clip(np.diff(seg.ele), 0, None).sum(),
        })
    out = pd.DataFrame(rows, columns=["start_idx", "end_idx", "start_s", "end_s", "duration_s", "distance_m",
                                      "avg_speed", "avg_pace_min_km", "avg_cadence_spm", "elev_gain_m"])
    out.index = [f"Rep {i + 1}" for i in range(len(out))]
    out.attrs["threshold"] = float(thr)
    return out


def label_phases(df: pd.DataFrame, intervals: pd.DataFrame) -> pd.DataFrame:
    """Add a 'phase' column: 'easy' or the rep name."""
    df = df.copy()
    df["phase"] = "easy"
    for name, r in intervals.iterrows():
        df.loc[int(r.start_idx):int(r.end_idx), "phase"] = name
    return df


def summarize(intervals: pd.DataFrame) -> pd.DataFrame:
    """Human-readable rep table."""
    return intervals.assign(
        start=intervals.start_s.map(lambda s: fmt_pace(s / 60)),
        duration=intervals.duration_s.map(lambda s: fmt_pace(s / 60)),
        distance_km=(intervals.distance_m / 1000).round(3),
        pace=intervals.avg_pace_min_km.map(fmt_pace),
        cadence_spm=intervals.avg_cadence_spm.round(0).astype("Int64"),
        elev_gain_m=intervals.elev_gain_m.round(1),
    )[["start", "duration", "distance_km", "pace", "cadence_spm", "elev_gain_m"]]


def recoveries(df: pd.DataFrame, intervals: pd.DataFrame) -> pd.DataFrame:
    """Duration, distance and pace of the gaps between consecutive reps."""
    rows = []
    for i in range(len(intervals) - 1):
        a, b = intervals.iloc[i], intervals.iloc[i + 1]
        seg = df.iloc[int(a.end_idx):int(b.start_idx) + 1]
        dist = seg.dist_m.iloc[-1] - seg.dist_m.iloc[0]
        dur = b.start_s - a.end_s
        rows.append({"between": f"{intervals.index[i]} -> {intervals.index[i + 1]}",
                     "duration": fmt_pace(dur / 60), "distance_m": round(dist),
                     "pace": fmt_pace(dur / 60 / (dist / 1000)) if dist else "-"})
    return pd.DataFrame(rows, columns=["between", "duration", "distance_m", "pace"]).set_index("between")


def analyze(gpx_path: str | Path, smooth_s: int = 15, cadence_factor: float = 2.0,
            min_work_s: float = 120, max_gap_s: float = 20, threshold: float | None = None):
    """Full pipeline: returns (points with phase labels, intervals, activity name)."""
    df, name = read_gpx(gpx_path)
    df = add_pace(df, smooth_s=smooth_s, cadence_factor=cadence_factor)
    intervals = detect_intervals(df, min_work_s=min_work_s, max_gap_s=max_gap_s, threshold=threshold)
    df = label_phases(df, intervals)
    return df, intervals, name
