"""Build the three.js 3D viewer for an analyzed session.

Writes index.html (from viewer/index.html) and data.js into the repo root. data.js carries
the track, the detected reps and (optionally) an OpenStreetMap ground texture; the page
loads viewer/style.css and viewer/app.js. Everything is local files, so the page opens
from file:// (only the three.js scripts and the font come from a CDN).

Map tiles come from tile.openstreetmap.org, are cached in data/tiles/ and are stitched,
desaturated and darkened into one JPEG that is embedded as a data URI.
Map data (c) OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

import base64
import io
import json
import math
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageEnhance

HERE = Path(__file__).parent
TEMPLATE_DIR = HERE / "viewer"
TILE_CACHE = HERE / "data" / "tiles"
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "interval-analysis/1.0 (personal training viewer; one-off tile fetch)"

MAP_ZOOM = 17            # ~1.2 m per pixel at Belgian latitudes
MAP_MARGIN_TILES = 1     # tiles of context around the route bounding box
MAP_BRIGHTNESS = 0.30    # 1.0 keeps OSM's own tones; lower fits the dark scene
MAP_CONTRAST = 1.35      # lift road/water edges before darkening
MAP_MAX_TILES = 600      # safety cap: refuse to fetch absurd areas


class Projection:
    """Meters east/north of the first GPS point (equirectangular, fine for a few km)."""

    def __init__(self, lat_ref: float, lon_ref: float, lat_mean: float):
        self.lat_ref, self.lon_ref = lat_ref, lon_ref
        self.k_east = 111_320 * math.cos(math.radians(lat_mean))

    def __call__(self, lat, lon):
        return (np.asarray(lon) - self.lon_ref) * self.k_east, (np.asarray(lat) - self.lat_ref) * 110_540


# --- OpenStreetMap ground texture -------------------------------------------
def lonlat_to_tile(lat, lon, z):
    n = 2 ** z
    lat_r = math.radians(lat)
    return (lon + 180) / 360 * n, (1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n


def tile_to_lonlat(x, y, z):
    n = 2 ** z
    return x / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def fetch_tile(z, x, y) -> Image.Image:
    path = TILE_CACHE / str(z) / str(x) / f"{y}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            path.write_bytes(r.read())
        time.sleep(0.05)  # be polite to the public tile server
    return Image.open(path).convert("RGB")


def build_map(points: pd.DataFrame, proj: Projection, out_dir: Path, zoom: int = MAP_ZOOM) -> dict:
    """Stitch the tiles covering the route; return bounds in local meters and a data URI."""
    x_a, y_a = lonlat_to_tile(points.lat.max(), points.lon.min(), zoom)  # north-west
    x_b, y_b = lonlat_to_tile(points.lat.min(), points.lon.max(), zoom)  # south-east
    x0, x1 = math.floor(x_a) - MAP_MARGIN_TILES, math.floor(x_b) + MAP_MARGIN_TILES
    y0, y1 = math.floor(y_a) - MAP_MARGIN_TILES, math.floor(y_b) + MAP_MARGIN_TILES
    cols, rows = x1 - x0 + 1, y1 - y0 + 1
    if cols * rows > MAP_MAX_TILES:
        raise RuntimeError(f"{cols * rows} tiles needed at zoom {zoom}; lower the zoom for this route")
    print(f"map: {cols * rows} tiles at zoom {zoom} ...", end=" ", flush=True)
    sheet = Image.new("RGB", (cols * 256, rows * 256))
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            sheet.paste(fetch_tile(zoom, tx, ty), ((tx - x0) * 256, (ty - y0) * 256))
    sheet = ImageEnhance.Contrast(sheet.convert("L")).enhance(MAP_CONTRAST)
    sheet = ImageEnhance.Brightness(sheet).enhance(MAP_BRIGHTNESS).convert("RGB")
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=82, optimize=True)
    lon_w, lat_n = tile_to_lonlat(x0, y0, zoom)
    lon_e, lat_s = tile_to_lonlat(x1 + 1, y1 + 1, zoom)
    e0, n1 = proj(lat_n, lon_w)
    e1, n0 = proj(lat_s, lon_e)
    print(f"{sheet.width}x{sheet.height} px, {buf.tell() / 1024:.0f} KB, covers {e1 - e0:.0f} x {n1 - n0:.0f} m")
    return {"x0": round(float(e0), 1), "x1": round(float(e1), 1), "n0": round(float(n0), 1), "n1": round(float(n1), 1),
            "uri": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")}


# --- Page data ---------------------------------------------------------------
def page_data(points: pd.DataFrame, intervals: pd.DataFrame, name: str, map_data: dict | None, proj: Projection) -> dict:
    east, north = proj(points.lat.values, points.lon.values)
    phase_names = ["easy"] + list(intervals.index)
    phase_idx = points.phase.map({p: i for i, p in enumerate(phase_names)}).fillna(0).astype(int)
    pace = points.pace_min_km.replace([np.inf, -np.inf], np.nan).fillna(20).clip(upper=20)
    return {
        "name": name,
        "start": str(points.time.iloc[0]),
        "phases": phase_names,
        "map": map_data,
        "reps": [
            {"name": n, "start": float(r.start_s), "end": float(r.end_s), "startIdx": int(r.start_idx),
             "endIdx": int(r.end_idx), "dist": float(r.distance_m), "pace": float(r.avg_pace_min_km),
             "cad": float(r.avg_cadence_spm) if np.isfinite(r.avg_cadence_spm) else 0.0}
            for n, r in intervals.iterrows()
        ],
        # columns: east, north, ele, t, dist, pace, cadence, phase
        "pts": [
            [round(float(e), 1), round(float(n), 1), round(float(z), 1) if np.isfinite(z) else 0.0, float(t),
             round(float(d), 1), round(float(p), 2), int(c), int(ph)]
            for e, n, z, t, d, p, c, ph in zip(east, north, points.ele, points.t, points.dist_m, pace,
                                                points.cadence_spm.fillna(0), phase_idx)
        ],
    }


def build_viewer(points: pd.DataFrame, intervals: pd.DataFrame, name: str, out_dir: str | Path,
                 with_map: bool = True) -> Path:
    """Write index.html and data.js into out_dir (the page loads viewer/style.css and viewer/app.js). Returns the index path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    proj = Projection(points.lat.iloc[0], points.lon.iloc[0], points.lat.mean())

    map_data = None
    if with_map:
        try:
            map_data = build_map(points, proj, out_dir)
        except Exception as exc:  # offline or tile server trouble: build without the map
            print(f"map: skipped ({exc})")

    data = page_data(points, intervals, name, map_data, proj)
    data_js = "const DATA = " + json.dumps(data, separators=(",", ":")) + ";\n"
    (out_dir / "data.js").write_text(data_js, encoding="utf-8")

    index = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8").replace("{{TITLE}}", f"{name} in 3D")
    (out_dir / "index.html").write_text(index, encoding="utf-8")
    print(f"viewer: {out_dir / 'index.html'} + data.js ({len(data_js) / 1024:.0f} KB)")
    return out_dir / "index.html"
