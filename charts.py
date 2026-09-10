"""Matplotlib charts for an analyzed session. Each function returns a Figure."""
from __future__ import annotations

from itertools import cycle
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from intervals import fmt_pace

# Categorical slots validated for color-vision deficiency; reps cycle through them.
C_BLUE, C_ORANGE, C_AQUA, C_YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
REP_COLORS = [C_BLUE, C_ORANGE, C_AQUA, C_YELLOW, "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
C_TEXT, C_MUTED, C_GRID = "#0b0b0b", "#52514e", "#e6e5e1"

STYLE = {
    "figure.dpi": 110, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": C_GRID, "axes.grid": True, "grid.color": C_GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.labelcolor": C_MUTED, "xtick.color": C_MUTED, "ytick.color": C_MUTED,
    "axes.titlecolor": C_TEXT, "axes.titlelocation": "left", "axes.titleweight": "bold",
    "axes.axisbelow": True, "font.size": 10,
}
plt.rcParams.update(STYLE)

pace_fmt = FuncFormatter(lambda v, _: fmt_pace(v))


def _shade(ax, intervals):
    for _, r in intervals.iterrows():
        ax.axvspan(r.start_s / 60, r.end_s / 60, color=C_ORANGE, alpha=0.10, lw=0)


def overview(df: pd.DataFrame, intervals: pd.DataFrame, name: str):
    """Pace, cadence and elevation over time, reps shaded."""
    thr = intervals.attrs.get("threshold")
    tmin = df["t"] / 60
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, gridspec_kw={"height_ratios": [3, 2, 1.5]})

    ax = axes[0]
    _shade(ax, intervals)
    ax.plot(tmin, df["pace_min_km"], color=C_BLUE, lw=2, label="Pace (smoothed)")
    if thr:
        ax.axhline(1000 / thr / 60, color=C_MUTED, lw=1, ls="--", label="Detection threshold")
    for rname, r in intervals.iterrows():
        ax.text((r.start_s + r.end_s) / 120, 5.05, f"{rname}\n{fmt_pace(r.avg_pace_min_km)} /km",
                ha="center", va="center", fontsize=9, color=C_TEXT)
    ax.set_ylim(14, 3.5)
    ax.yaxis.set_major_formatter(pace_fmt)
    ax.set_ylabel("Pace (min/km)")
    ax.set_title(f"{name}: pace, cadence and elevation")
    ax.legend(loc="lower left", frameon=False)

    ax = axes[1]
    _shade(ax, intervals)
    ax.plot(tmin, df["cadence_spm"].rolling(15, center=True).mean(), color=C_AQUA, lw=2)
    ax.set_ylabel("Cadence (steps/min)")
    ax.set_ylim(80, 200)

    ax = axes[2]
    _shade(ax, intervals)
    ax.fill_between(tmin, df["ele"], df["ele"].min() - 1, color=C_YELLOW, alpha=0.25, lw=0)
    ax.plot(tmin, df["ele"], color=C_YELLOW, lw=1.5)
    ax.set_ylabel("Elevation (m)")
    ax.set_xlabel("Elapsed time (min)")
    ax.set_xlim(0, tmin.iloc[-1])
    fig.tight_layout()
    return fig


def rep_pace(df: pd.DataFrame, intervals: pd.DataFrame):
    """Pace inside each rep, aligned to rep start."""
    fig, ax = plt.subplots(figsize=(10, 4.5))
    lo, hi = np.inf, -np.inf
    for (rname, r), color in zip(intervals.iterrows(), cycle(REP_COLORS)):
        seg = df.iloc[int(r.start_idx):int(r.end_idx) + 1]
        x = (seg["t"] - r.start_s) / 60
        ax.plot(x, seg["pace_min_km"], color=color, lw=2, label=f"{rname}  {fmt_pace(r.avg_pace_min_km)} /km")
        lo, hi = min(lo, seg["pace_min_km"].min()), max(hi, seg["pace_min_km"].quantile(0.98))
    if np.isfinite(lo):
        ax.set_ylim(hi + 0.3, lo - 0.2)
    ax.yaxis.set_major_formatter(pace_fmt)
    ax.set_xlabel("Time into rep (min)")
    ax.set_ylabel("Pace (min/km)")
    ax.set_title("Pace inside each rep (faster is higher)")
    if len(intervals):
        ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    return fig


def rep_summary(intervals: pd.DataFrame):
    """Average pace, distance and cadence per rep."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    x = np.arange(len(intervals))

    def bars(ax, values, title, fmt):
        b = ax.bar(x, values, width=0.55, color=C_BLUE, edgecolor="#fcfcfb", linewidth=2)
        for rect, v in zip(b, values):
            ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(), fmt(v),
                    ha="center", va="bottom", fontsize=9, color=C_TEXT)
        ax.set_xticks(x, intervals.index)
        ax.set_title(title)
        ax.grid(axis="x", visible=False)
        if len(values) and np.isfinite(values).any():
            ax.set_ylim(0, np.nanmax(values) * 1.15)

    bars(axes[0], intervals.avg_pace_min_km.values, "Average pace (min/km)", fmt_pace)
    axes[0].yaxis.set_major_formatter(pace_fmt)
    bars(axes[1], intervals.distance_m.values, "Distance (m)", lambda v: f"{v:.0f}")
    bars(axes[2], intervals.avg_cadence_spm.values, "Cadence (steps/min)", lambda v: f"{v:.0f}")
    fig.tight_layout()
    return fig


def pace_histogram(df: pd.DataFrame, intervals: pd.DataFrame):
    """Seconds spent at each pace, work vs. easy."""
    thr = intervals.attrs.get("threshold")
    work = df["phase"].str.startswith("Rep")
    fig, ax = plt.subplots(figsize=(9, 3.5))
    bins = np.linspace(3.5, 14, 60)
    ax.hist(df.loc[~work, "pace_min_km"].clip(upper=14), bins=bins, color=C_MUTED, alpha=0.6, label="Easy / walking")
    ax.hist(df.loc[work, "pace_min_km"].clip(upper=14), bins=bins, color=C_ORANGE, alpha=0.8, label="Work intervals")
    if thr:
        p = 1000 / thr / 60
        ax.axvline(p, color=C_TEXT, lw=1, ls="--")
        ax.text(p, ax.get_ylim()[1] * 0.95, f" threshold {fmt_pace(p)} /km", va="top", fontsize=9)
    ax.xaxis.set_major_formatter(pace_fmt)
    ax.set_xlabel("Pace (min/km)")
    ax.set_ylabel("Seconds")
    ax.set_title("Time spent at each pace")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def route(df: pd.DataFrame, intervals: pd.DataFrame):
    """Route in local meters, reps highlighted."""
    lat0 = df.lat.mean()
    xm = (df.lon - df.lon.iloc[0]) * 111_320 * np.cos(np.radians(lat0))
    ym = (df.lat - df.lat.iloc[0]) * 110_540
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.plot(xm, ym, color=C_MUTED, lw=1.5, alpha=0.5, label="Easy / recovery")
    for (rname, r), color in zip(intervals.iterrows(), cycle(REP_COLORS)):
        sl = slice(int(r.start_idx), int(r.end_idx) + 1)
        ax.plot(xm[sl], ym[sl], color=color, lw=3, label=rname)
        ax.plot(xm[sl].iloc[0], ym[sl].iloc[0], "o", color=color, ms=8, mec="#fcfcfb", mew=2)
    ax.plot(xm.iloc[0], ym.iloc[0], "s", color=C_TEXT, ms=8, label="Start")
    ax.set_aspect("equal")
    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")
    ax.set_title("Route, work intervals highlighted")
    ax.legend(frameon=False, loc="best")
    fig.tight_layout()
    return fig


ALL = {
    "overview": lambda df, iv, name: overview(df, iv, name),
    "rep_pace": lambda df, iv, name: rep_pace(df, iv),
    "rep_summary": lambda df, iv, name: rep_summary(iv),
    "pace_histogram": lambda df, iv, name: pace_histogram(df, iv),
    "route": lambda df, iv, name: route(df, iv),
}


def save_all(df: pd.DataFrame, intervals: pd.DataFrame, name: str, out_dir: str | Path) -> list[Path]:
    """Write every chart as PNG into out_dir; returns the paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for key, make in ALL.items():
        fig = make(df, intervals, name)
        p = out_dir / f"{key}.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        paths.append(p)
    return paths
