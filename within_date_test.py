"""Date-block bootstrap and within-date threshold permutation for spatial AUC."""
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

SEED = 20261106
N_REPS = 2000


def main():
    rng = np.random.default_rng(SEED)
    labels = pd.read_csv("outputs/label_table.csv", parse_dates=["date"])
    predictions = pd.read_csv("outputs/label_table_oof_predictions.csv", parse_dates=["date"])
    event_dates = labels.loc[labels.label.eq(1), "date"].unique()
    groups = [g for _, g in labels[labels.date.isin(event_dates)].groupby("date")
              if g.label.nunique() == 2]
    pred_groups = [g for _, g in predictions[predictions.date.isin(event_dates)].groupby("date")
                   if g.label.nunique() == 2]
    stats = []
    for col in ("physics_ratio",):
        daily = np.array([roc_auc_score(g.label, g[col]) for g in groups])
        boot = np.array([rng.choice(daily, len(daily), replace=True).mean() for _ in range(N_REPS)])
        stats.append({"metric": "mean_date_auc", "score": col, "estimate": daily.mean(),
                      "n_dates": len(daily), "ci95_low": np.quantile(boot, .025),
                      "ci95_high": np.quantile(boot, .975), "null_mean": np.nan,
                      "null95_low": np.nan, "null95_high": np.nan, "p_two_sided": np.nan})
    for col in ("logit_rain_physics",):
        daily = np.array([roc_auc_score(g.label, g[col]) for g in pred_groups])
        boot = np.array([rng.choice(daily, len(daily), replace=True).mean() for _ in range(N_REPS)])
        stats.append({"metric": "mean_date_auc", "score": col, "estimate": daily.mean(),
                      "n_dates": len(daily), "ci95_low": np.quantile(boot, .025),
                      "ci95_high": np.quantile(boot, .975), "null_mean": np.nan,
                      "null95_low": np.nan, "null95_high": np.nan, "p_two_sided": np.nan})

    thresholds = labels.drop_duplicates("id").set_index("id").i_crit_mm_h
    null = np.empty(N_REPS)
    observed_daily = np.array([roc_auc_score(g.label, g.physics_ratio) for g in groups])
    for i in range(N_REPS):
        daily_aucs = []
        for g in groups:
            shuffled = rng.permutation(g.id.map(thresholds).to_numpy())
            scores = g.rain_peak_1h.to_numpy() / shuffled
            daily_aucs.append(roc_auc_score(g.label, scores))
        null[i] = np.mean(daily_aucs)
    observed = observed_daily.mean()
    p = (1 + np.sum(np.abs(null - .5) >= abs(observed - .5))) / (N_REPS + 1)
    stats.append({"metric": "within_date_threshold_shuffle", "score": "rain_peak_1h / shuffled i_crit_mm_h",
                  "estimate": observed, "n_dates": len(groups), "ci95_low": np.nan,
                  "ci95_high": np.nan, "null_mean": null.mean(),
                  "null95_low": np.quantile(null, .025), "null95_high": np.quantile(null, .975),
                  "p_two_sided": p})
    out = pd.DataFrame(stats)
    out.to_csv("outputs/within_date_spatial_test.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
