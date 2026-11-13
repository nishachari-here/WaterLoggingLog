"""GraphSAGE-style hotspot-day model with leave-one-hotspot-out evaluation."""
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.preprocessing import StandardScaler
from torch import nn
import torch.nn.functional as F

import config

FEATURES = ["rain_peak_1h_log", "rain_3h_log", "rain_24h_log", "hand_m",
            "depression_m", "upstream_km2_log", "twi", "tpi300_m", "physics_ratio"]


class GraphSAGE(nn.Module):
    def __init__(self, n_features, hidden=32):
        super().__init__()
        self.self1 = nn.Linear(n_features, hidden)
        self.neighbor1 = nn.Linear(n_features, hidden, bias=False)
        self.self2 = nn.Linear(hidden, hidden)
        self.neighbor2 = nn.Linear(hidden, hidden, bias=False)
        self.out = nn.Linear(hidden, 1)

    def forward(self, x, adj):
        h = F.relu(self.self1(x) + self.neighbor1(adj @ x))
        h = F.relu(self.self2(h) + self.neighbor2(adj @ h))
        return self.out(h).squeeze(-1)


def run():
    df = pd.read_csv(config.OUT_DIR / "label_table.csv")
    df = df[df.wet_season].copy().reset_index(drop=True)
    nodes = pd.read_csv(config.OUT_DIR / "hotspot_graph_nodes.csv").drop_duplicates("id")
    ids = sorted(nodes.id)
    idx = {name: i for i, name in enumerate(ids)}
    coords = nodes.set_index("id").loc[ids][["node_lat", "node_lon"]].to_numpy()
    dist = np.sqrt(((coords[:, None] - coords[None, :]) ** 2).sum(axis=2))
    adj = torch.tensor((dist < 0.08).astype(np.float32), dtype=torch.float32)
    adj.fill_diagonal_(1)
    adj /= adj.sum(1, keepdim=True).clamp_min(1)
    scaler = StandardScaler().fit(df[FEATURES])
    dates = sorted(df.date.unique())
    date_index = {d: i for i, d in enumerate(dates)}
    row_hotspot = df.id.map(idx).to_numpy()
    row_date = df.date.map(date_index).to_numpy()
    x_np = np.zeros((len(dates), len(ids), len(FEATURES)), dtype=np.float32)
    y_np = np.zeros((len(dates), len(ids)), dtype=np.float32)
    for r, (_, row) in enumerate(df.iterrows()):
        x_np[row_date[r], row_hotspot[r]] = scaler.transform(row[FEATURES].to_frame().T)[0]
        y_np[row_date[r], row_hotspot[r]] = row.label
    x = torch.tensor(x_np)
    y = torch.tensor(y_np)
    oof = np.zeros(len(df), dtype=float)
    for held, held_id in enumerate(ids):
        tr = torch.ones(len(ids), dtype=torch.bool)
        tr[held] = False
        model = GraphSAGE(len(FEATURES))
        opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=1e-3)
        pos_weight = torch.tensor(float((y[:, tr] == 0).sum() / max(int((y[:, tr] == 1).sum()), 1)))
        for _ in range(60):
            opt.zero_grad()
            logits = model(x, adj)
            loss = F.binary_cross_entropy_with_logits(logits[:, tr], y[:, tr], pos_weight=pos_weight)
            loss.backward()
            opt.step()
        with torch.no_grad():
            scores = torch.sigmoid(model(x, adj)[:, held]).numpy()
            rows = np.flatnonzero(df.id.to_numpy() == held_id)
            oof[rows] = scores[row_date[rows]]
    labels = df.label.to_numpy()
    result = {"model": "graphsage_hotspot_loho", "auc": roc_auc_score(labels, oof),
              "average_precision": average_precision_score(labels, oof), "n": len(df),
              "positives": int(labels.sum()), "hotspots": len(ids)}
    pd.DataFrame([result]).to_csv(config.OUT_DIR / "graphsage_metrics.csv", index=False)
    pd.DataFrame({"date": df.date, "id": df.id, "label": labels, "score": oof}).to_csv(
        config.OUT_DIR / "graphsage_oof.csv", index=False)
    print(result)
    return result


if __name__ == "__main__":
    run()
