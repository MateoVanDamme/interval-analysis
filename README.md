# interval-analysis

Two parts:

1. **Detect intervals.** `interval_analysis.ipynb` reads a Strava GPX export from `data/`, derives pace from GPS, and automatically finds the hard reps (speed threshold plus minimum duration). It writes `data/*_processed.csv` and `data/*_intervals.csv`.
2. **Visualize.** `build_gpx_3d.py` turns those CSVs into `index.html`, a three.js 3D replay where height and color show pace and the reps stand out as crimson curtains.

```
python -m nbconvert --to notebook --execute --inplace interval_analysis.ipynb
python build_gpx_3d.py
```

Then open `index.html`. Needs pandas, numpy, matplotlib and nbconvert.
