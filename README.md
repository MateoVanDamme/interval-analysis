# interval-analysis

My last training before the [Stratenloop Tom Van Hooste](https://www.kleinsinaaileeft.be/loopwedstrijdinformatie.html) in Klein-Sinaai: 4 laps of a 2.80 km loop, 11.2 km in total. My time there in 2024 was 1:01'20" (36th, men's 12 km).

Two parts:

1. **Detect intervals.** `interval_analysis.ipynb` reads a Strava GPX export from `data/`, derives pace from GPS, and automatically finds the hard reps (speed threshold plus minimum duration). It writes `data/*_processed.csv` and `data/*_intervals.csv`.
2. **Visualize.** `build_gpx_3d.py` turns those CSVs into `index.html` plus `style.css`, a three.js 3D replay where height and color show pace and the reps stand out as crimson curtains.

```
python -m nbconvert --to notebook --execute --inplace interval_analysis.ipynb
python build_gpx_3d.py
```

Then open `index.html`. Needs pandas, numpy, matplotlib and nbconvert.
