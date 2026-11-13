"""Stage 1 baseline: where does it flood? Official BBMP flood points vs terrain. Run after run_terrain.py.

    .venv\\Scripts\\python run_stage1.py
"""
import pandas as pd

from pipeline import stage1


def main():
    pd.set_option("display.width", 200)
    summary, by_zone, n_pos, n_bg = stage1.run()
    print(f"{n_pos} flood points, {n_bg} background points, one zone held out at a time\n")
    print(summary.to_string(index=False))
    print("\nRandom Forest by held-out zone:")
    print(by_zone[by_zone.model == "random_forest"].drop(columns="model").to_string(index=False))


if __name__ == "__main__":
    main()
