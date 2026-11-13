"""Lead-time backtest (2024-2025): how many days ahead would the dashboard have warned? Run after run_backtest.py.

    .venv\\Scripts\\python run_leadtime.py
"""
import pandas as pd

from pipeline import leadtime


def main():
    pd.set_option("display.width", 220)
    skill, alerts, events, factor = leadtime.run()
    print(f"forecast scaled x{factor:.1f} (median gauge/model ratio from run_backtest.py)\n")
    print("Skill by lead (rank-based):")
    print(skill.round(3).to_string(index=False))
    print("\nDashboard alerts by lead:")
    print(alerts.to_string(index=False))
    print("\nPer documented flood:")
    print(events.to_string(index=False))


if __name__ == "__main__":
    main()
