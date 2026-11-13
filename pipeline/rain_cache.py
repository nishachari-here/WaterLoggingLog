"""Model-tagged cache helpers for Open-Meteo historical hourly rain."""
from datetime import date
import json
from pathlib import Path

import pandas as pd


def cache_paths(raw_dir: Path, model: str):
    stem = f"hist_forecast_hourly_{model}_0p25deg"
    folder = raw_dir / "rain"
    return folder / f"{stem}.csv", folder / f"{stem}.json"


def read_cache(raw_dir: Path, model: str):
    csv_path, meta_path = cache_paths(raw_dir, model)
    if not csv_path.exists() and not meta_path.exists():
        return None
    if not meta_path.exists():
        raise RuntimeError(f"Rain cache {csv_path} has no model metadata; refusing untagged cache")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if metadata.get("model") != model or metadata.get("grid") != "0.25deg":
        raise RuntimeError(f"Rain cache metadata does not match {model} at 0.25 degree grid")
    return pd.read_csv(csv_path, parse_dates=["time"])


def write_cache(raw_dir: Path, model: str, frame: pd.DataFrame, grid_locations):
    csv_path, meta_path = cache_paths(raw_dir, model)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_path, index=False)
    meta_path.write_text(json.dumps({"model": model, "grid": "0.25deg",
                                     "fetched_at": date.today().isoformat(),
                                     "returned_grid_locations": grid_locations}, indent=2), encoding="utf-8")
