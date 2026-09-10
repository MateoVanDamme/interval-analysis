# interval-analysis

My last training before the [Stratenloop Tom Van Hooste](https://www.kleinsinaaileeft.be/loopwedstrijdinformatie.html) in Klein-Sinaai: 4 laps of a 2.80 km loop, 11.2 km in total. My time there in 2024 was 1:01'20" (36th, men's 12 km).

Live at [mateovandamme.github.io/interval-analysis](https://mateovandamme.github.io/interval-analysis/).

Two parts:

1. **Detect intervals.** `intervals.py` reads a Strava GPX export, derives pace from GPS, and automatically finds the hard reps (speed threshold from a two-means split plus a minimum duration).
2. **Visualize.** `charts.py` draws the summary charts, `viewer.py` builds a three.js 3D replay where height and color show pace, the reps stand out as crimson curtains, and the ground is an OpenStreetMap raster of the area.

## Run

```
pip install pandas numpy matplotlib pillow
python run.py data/3_x_5min.gpx
```

This regenerates `index.html`, `data.js`, `charts/*.png`, `data/points.csv` and `data/intervals.csv`. Any other Strava GPX works the same way; commit the result and Pages serves it. Options: `--min-work 60` (shorter reps), `--max-gap 10`, `--threshold 3.0` (m/s, instead of automatic), `--cadence-factor 1` (device already writes steps/min), `--no-map`.

The viewer's HTML, CSS and JS live in `viewer/`. The notebook walks through the same pipeline interactively.

Map data © OpenStreetMap contributors, ODbL.
