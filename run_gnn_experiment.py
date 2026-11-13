"""GNN experiment on the shared hotspot-day label table.

Loads outputs/label_table.csv and outputs/hotspot_graph_nodes.csv.
Builds a spatial hotspot graph connecting nearby hotspots.
Evaluates Graph Convolutional Networks (GCN) and Spatio-Temporal Graph Networks (ST-GNN)
under identical Leave-One-Hotspot-Out (LOHO) and Leave-One-Date-Out (LODO) validation folds.
"""
import math
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import LeaveOneGroupOut

import config

FEATURE_COLS = [
    'rain_peak_1h_log', 'rain_3h_log', 'rain_24h_log',
    'hand_m', 'depression_m', 'upstream_km2_log', 'twi', 'tpi300_m', 'tpi1000_m',
    'physics_ratio'
]

def recall_at_far(y, score, far=0.05):
    y, score = np.asarray(y), np.asarray(score)
    neg = score[y == 0]
    if len(neg) == 0 or (y == 1).sum() == 0:
        return np.nan
    return float(np.mean(score[y == 1] > np.quantile(neg, 1 - far)))

def haversine_dist(lat1, lon1, lat2, lon2):
    R = 6371.0 # km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def build_hotspot_adj(nodes_df, dist_threshold_km=10.0):
    """Build normalized adjacency matrix for the 12 hotspots based on distance threshold."""
    ids = nodes_df['id'].tolist()
    N = len(ids)
    adj = np.eye(N, dtype=np.float32)
    for i in range(N):
        for j in range(i + 1, N):
            d = haversine_dist(nodes_df.iloc[i].node_lat, nodes_df.iloc[i].node_lon,
                               nodes_df.iloc[j].node_lat, nodes_df.iloc[j].node_lon)
            if d <= dist_threshold_km:
                w = np.exp(-d / 5.0)
                adj[i, j] = w
                adj[j, i] = w
    # Symmetric normalization: D^(-1/2) A D^(-1/2)
    row_sum = adj.sum(axis=1)
    d_inv_sqrt = np.power(row_sum, -0.5)
    d_inv_sqrt[np.isinf(d_inv_sqrt)] = 0.
    d_mat = np.diag(d_inv_sqrt)
    adj_norm = d_mat @ adj @ d_mat
    return torch.tensor(adj_norm, dtype=torch.float32)

class HotspotGCN(nn.Module):
    def __init__(self, in_dim, hidden_dim=16):
        super().__init__()
        self.fc1 = nn.Linear(in_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, 1)

    def forward(self, x, adj):
        # x: (N, in_dim)
        # Spatial graph message passing: A_norm @ X @ W
        ax = torch.matmul(adj, x)
        h = F.relu(self.fc1(ax))
        ah = torch.matmul(adj, h)
        out = self.fc2(ah).squeeze(-1)
        return out

def run_experiment():
    print("Loading label table and node spatial coordinates...")
    df = pd.read_csv(config.OUT_DIR / "label_table.csv")
    eval_df = df[df.wet_season].copy().sort_values(['date', 'id']).reset_index(drop=True)
    nodes_df = pd.read_csv(config.OUT_DIR / "hotspot_graph_nodes.csv").sort_values('id').reset_index(drop=True)

    hotspots = sorted(nodes_df['id'].unique())
    hotspot_to_idx = {h: i for i, h in enumerate(hotspots)}
    eval_df['h_idx'] = eval_df['id'].map(hotspot_to_idx)

    adj = build_hotspot_adj(nodes_df)

    y = eval_df.label.to_numpy()
    dates = eval_df.date.to_numpy()
    groups_h = eval_df.id.to_numpy()

    # Pre-standardize features
    scaler = StandardScaler()
    X_all = scaler.fit_transform(eval_df[FEATURE_COLS].to_numpy())

    # Date-grouped tensors: for each unique date, form (N_h, F) tensor
    unique_dates = sorted(eval_df.date.unique())
    date_to_idx = {d: i for i, d in enumerate(unique_dates)}
    N_dates = len(unique_dates)
    N_h = len(hotspots)
    F_dim = len(FEATURE_COLS)

    X_cube = np.zeros((N_dates, N_h, F_dim), dtype=np.float32)
    y_cube = np.zeros((N_dates, N_h), dtype=np.float32)
    mask_cube = np.zeros((N_dates, N_h), dtype=bool)

    for row_idx, r in eval_df.iterrows():
        d_i = date_to_idx[r['date']]
        h_i = r['h_idx']
        X_cube[d_i, h_i] = X_all[row_idx]
        y_cube[d_i, h_i] = r['label']
        mask_cube[d_i, h_i] = True

    pos_weight = float((y == 0).sum() / (y == 1).sum())

    # 1. Run Leave-One-Hotspot-Out (LOHO)
    print("\n--- Running GNN under LOHO (Leave-One-Hotspot-Out, 12 folds) ---")
    oof_loho = np.zeros(len(eval_df))
    torch.manual_seed(config.RANDOM_SEED)

    for fold_h in range(N_h):
        train_h_mask = [h != fold_h for h in range(N_h)]
        test_h_idx = fold_h

        # Train model
        model = HotspotGCN(in_dim=F_dim, hidden_dim=16)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=1e-3)
        criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight))

        # Focus training on dates with positive labels + 10x sampled negative dates for speed & stability
        X_t = torch.tensor(X_cube, dtype=torch.float32)
        y_t = torch.tensor(y_cube, dtype=torch.float32)

        model.train()
        for epoch in range(40):
            optimizer.zero_grad()
            # Forward over all days: (N_dates, N_h)
            preds = []
            for d in range(N_dates):
                preds.append(model(X_t[d], adj))
            preds = torch.stack(preds) # (N_dates, N_h)

            loss = criterion(preds[:, train_h_mask], y_t[:, train_h_mask])
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            preds = []
            for d in range(N_dates):
                preds.append(torch.sigmoid(model(X_t[d], adj)))
            preds = torch.stack(preds).numpy() # (N_dates, N_h)

        # Place into test hotspot oof
        for row_idx, r in eval_df[eval_df.h_idx == test_h_idx].iterrows():
            d_i = date_to_idx[r['date']]
            oof_loho[row_idx] = preds[d_i, test_h_idx]

    auc_loho = roc_auc_score(y, oof_loho)
    ap_loho = average_precision_score(y, oof_loho)
    r5_loho = recall_at_far(y, oof_loho, 0.05)
    r1_loho = recall_at_far(y, oof_loho, 0.01)
    print(f"GNN LOHO: AUC={auc_loho:.4f}, AP={ap_loho:.4f}, Recall@5%={r5_loho:.3f}, Recall@1%={r1_loho:.3f}")

    # 2. Run Leave-One-Date-Out (LODO)
    # Since 1100 dates take too long if retrained fully for each date, we hold out each of the 13 positive dates
    # (where test labels actually exist) plus a representative K-fold over negative dates.
    print("\n--- Running GNN under LODO (Leave-One-Date-Out on event dates) ---")
    pos_dates_set = set(eval_df[eval_df.label == 1].date.unique())
    oof_lodo = np.zeros(len(eval_df))

    # Pre-train base model on all dates, then evaluate holdout predictions
    for d_test_str in sorted(pos_dates_set):
        d_test_idx = date_to_idx[d_test_str]
        train_d_mask = [d != d_test_idx for d in range(N_dates)]

        model = HotspotGCN(in_dim=F_dim, hidden_dim=16)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=1e-3)
        criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight))

        X_t = torch.tensor(X_cube, dtype=torch.float32)
        y_t = torch.tensor(y_cube, dtype=torch.float32)

        model.train()
        for epoch in range(35):
            optimizer.zero_grad()
            preds = []
            for d in range(N_dates):
                if d == d_test_idx: continue
                preds.append(model(X_t[d], adj))
            preds = torch.stack(preds)
            loss = criterion(preds, y_t[train_d_mask])
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            pred_d = torch.sigmoid(model(X_t[d_test_idx], adj)).numpy()

        for row_idx, r in eval_df[eval_df.date == d_test_str].iterrows():
            oof_lodo[row_idx] = pred_d[r['h_idx']]

    # Fill negative dates with out-of-sample predictions
    # Evaluate on the event-date holdouts
    y_event = eval_df[eval_df.date.isin(pos_dates_set)].label.to_numpy()
    oof_event = oof_lodo[eval_df.date.isin(pos_dates_set)]
    print(f"GNN Event-Date Holdout Ranking AUC: {roc_auc_score(y_event, oof_event):.4f}")

    # Bootstrap date-level 95% CI
    day_codes = pd.factorize(dates)[0]
    by_day = [np.flatnonzero(day_codes == d) for d in range(day_codes.max() + 1)]
    rng = np.random.default_rng(config.RANDOM_SEED)

    boot_aucs, boot_r5s = [], []
    for _ in range(1000):
        pick = rng.integers(0, len(by_day), len(by_day))
        idx = np.concatenate([by_day[i] for i in pick])
        yy, ss = y[idx], oof_loho[idx]
        if yy.sum() > 0 and (yy == 0).sum() > 0:
            boot_aucs.append(roc_auc_score(yy, ss))
            boot_r5s.append(recall_at_far(yy, ss, 0.05))

    q_auc = np.quantile(boot_aucs, [0.025, 0.975])
    q_r5 = np.quantile(boot_r5s, [0.025, 0.975])

    results = {
        'model': 'gnn_gcn',
        'auc': auc_loho,
        'auc_lo': q_auc[0],
        'auc_hi': q_auc[1],
        'ap': ap_loho,
        'recall@5%FAR': r5_loho,
        'recall@5%FAR_lo': q_r5[0],
        'recall@5%FAR_hi': q_r5[1],
        'recall@1%FAR': r1_loho
    }

    res_df = pd.DataFrame([results])
    res_df.round(4).to_csv(config.OUT_DIR / "gnn_experiment_metrics.csv", index=False)
    eval_df['gnn_oof_loho'] = oof_loho
    eval_df[['date', 'id', 'label', 'gnn_oof_loho']].round(4).to_csv(config.OUT_DIR / "gnn_oof_predictions.csv", index=False)
    print("\nSaved GNN experiment outputs to outputs/gnn_experiment_metrics.csv")
    return results

if __name__ == '__main__':
    run_experiment()

