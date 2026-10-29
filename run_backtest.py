"""Backtest on 2022-2025 monsoons against news-documented flood days. Run after run_network.py.

    .venv\\Scripts\\python run_backtest.py
"""
import pandas as pd

from pipeline import backtest


def main():
    pd.set_option("display.width", 200)
    table, days, spatial, bias, per_hotspot, df = backtest.run()
    print(f"hotspot-days: {len(df)}  flood labels: {int(df.label.sum())}")
    print("\nMethod comparison (hotspot-days):")
    print(table.to_string(index=False))
    print("\nCity-level day detection:", {k: round(v, 3) if isinstance(v, float) else v for k, v in days.items()})
    print("\nLabels per hotspot (media attention check):")
    print(per_hotspot.to_string())
    print("\nOpen-Meteo vs reported rain on documented days:")
    print(bias.to_string(index=False))
    print(f"median reported/model ratio: {bias.ratio.median():.1f}")


if __name__ == "__main__":
    main()
