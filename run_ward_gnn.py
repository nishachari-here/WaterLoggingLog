"""Spatial ward graph classifier, trained through 2023 and tested on 2024–2025."""
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.preprocessing import StandardScaler
from torch import nn
import torch.nn.functional as F

import config
from pipeline import stage2

FEATURES = ["rain", "rain_lag1", "rain_3d", "rain_ante7", "peak", "peak_2d",
            "sm_prev", "drain_30d", "month", "n_flood_pts", "flood_pts_per_km2",
            "hand_mean", "hand_lt2_frac", "twi_mean", "depression_depth_mean",
            "terrain_score_mean", "area_km2"]


class WardGraphNet(nn.Module):
    def __init__(self, n_features, hidden=32):
        super().__init__()
        self.self_layer = nn.Linear(n_features, hidden)
        self.neighbor_layer = nn.Linear(n_features, hidden, bias=False)
        self.out = nn.Linear(hidden, 1)

    def forward(self, x, adj):
        return self.out(F.relu(self.self_layer(x) + self.neighbor_layer(adj @ x))).squeeze(-1)


def run():
    df = stage2.build_table().sort_values(["date", "ward"]).reset_index(drop=True)
    wards = sorted(df.ward.unique())
    geom = stage2.labels.wards().set_index("ward").loc[wards].geometry
    touching = np.zeros((len(wards), len(wards)), dtype=np.float32)
    for i, a in enumerate(geom):
        for j in range(i + 1, len(wards)):
            if a.touches(geom.iloc[j]) or a.intersects(geom.iloc[j]):
                touching[i, j] = touching[j, i] = 1
    np.fill_diagonal(touching, 1)
    deg = np.maximum(touching.sum(1), 1)
    adj = torch.tensor(touching / deg[:, None], dtype=torch.float32)
    train_mask = df.date < "2024-01-01"
    test_mask = df.date >= "2024-01-01"
    scaler = StandardScaler().fit(df.loc[train_mask, FEATURES])
    x = torch.tensor(scaler.transform(df[FEATURES]), dtype=torch.float32)
    y = torch.tensor(df.y.to_numpy(), dtype=torch.float32)
    train = torch.tensor(train_mask.to_numpy())
    test = np.flatnonzero(test_mask)
    model = WardGraphNet(len(FEATURES))
    opt = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=1e-3)
    pos_weight = torch.tensor(float((y[train] == 0).sum() / max(int((y[train] == 1).sum()), 1)))
    for _ in range(80):
        opt.zero_grad()
        loss = F.binary_cross_entropy_with_logits(model(x, adj), y, pos_weight=pos_weight)
        loss.backward()
        opt.step()
    with torch.no_grad():
        score = torch.sigmoid(model(x, adj)).numpy()[test]
    truth = y.numpy()[test]
    result = {"model": "ward_graph_gnn_time_split", "train_end": "2023-12-31",
              "test_start": "2024-01-01", "auc": roc_auc_score(truth, score),
              "average_precision": average_precision_score(truth, score), "n_test": len(test),
              "positives_test": int(truth.sum()), "wards": len(wards)}
    pd.DataFrame([result]).to_csv(config.OUT_DIR / "ward_gnn_metrics.csv", index=False)
    pd.DataFrame({"date": df.iloc[test].date, "ward": df.iloc[test].ward,
                  "label": truth, "score": score}).to_csv(config.OUT_DIR / "ward_gnn_predictions.csv", index=False)
    print(result)
    return result


if __name__ == "__main__":
    run()
