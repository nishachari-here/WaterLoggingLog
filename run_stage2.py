"""Stage 2 baseline: which wards report flooding on which day? Run after run_terrain.py.

    .venv\\Scripts\\python run_stage2.py
"""
import pandas as pd

from pipeline import stage2


def main():
    pd.set_option("display.width", 200)
    table, info = stage2.run()
    print(f"{info['wards']} wards, {info['ward_days']} ward-days, {info['positives']} with a flood complaint")
    print(f"train (2020-2023): {info['train']} rows, {info['train_pos']} positive")
    print(f"test (2024 to Jun 2025): {info['test']} rows, {info['test_pos']} positive\n")
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
