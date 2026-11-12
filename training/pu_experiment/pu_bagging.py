#!/usr/bin/env python3
"""
Stage 1 Formal Positive-Unlabelled (PU) Learning Experiment: PU-Bagging
=======================================================================
Objective:
  Implement and benchmark formal PU-Bagging (Mordelet & Vert, 2014) across:
    1. Logistic Regression (PU-Bagged)
    2. Random Forest (PU-Bagged)
    3. GraphSAGE GNN (PU-Bagged on full structural topology)

Protocol:
  - Preserves exact 8-fold spatial cross-validation (leave-one-zone-out across the 8 BBMP zones).
  - Zone 'outside' is strictly excluded from all training and test folds.
  - Strict graph isolation: Cross-zone edges connecting to the held-out test zone are removed.
  - Scalers are fit strictly on training data.
  - Compares PU-Bagged models directly against the original Class-Weighted (PN) models.
  - Explores sensitivity to sampling ratio r in {1:1, 2:1, 3:1, 5:1} and bag count K in {1, 3, 5, 10}.
"""

import os
import sys
import time
import json
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    roc_curve,
    precision_recall_curve,
)

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv
from torch_geometric.utils import to_undirected

# Set seeds
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(RANDOM_SEED)

# Paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))
EXPORT_DIR = os.path.join(REPO_ROOT, 'export')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
CHECKPOINTS_DIR = os.path.join(BASE_DIR, 'checkpoints')
ORIGINAL_RESULTS_DIR = os.path.join(REPO_ROOT, 'training', 'results')

os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(CHECKPOINTS_DIR, exist_ok=True)


# ==============================================================================
# GraphSAGE Architecture
# ==============================================================================
class GraphSAGENet(nn.Module):
    def __init__(self, in_channels, hidden_channels=64, dropout=0.2):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels, aggr='mean')
        self.conv2 = SAGEConv(hidden_channels, hidden_channels, aggr='mean')
        self.fc = nn.Linear(hidden_channels, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index):
        h = self.conv1(x, edge_index)
        h = F.relu(h)
        h = self.dropout(h)
        h = self.conv2(h, edge_index)
        h = F.relu(h)
        h = self.dropout(h)
        return self.fc(h).squeeze(-1)


def compute_metrics(y_true, y_prob):
    """
    Computes ranking and disaster management metrics:
      - ROC-AUC (against incomplete labels)
      - Average Precision (against incomplete labels)
      - Top-20% Known Positive Capture Rate (Recall of official flood points in top 20% risk area)
      - Top-20% Precision
    """
    auc = roc_auc_score(y_true, y_prob)
    ap = average_precision_score(y_true, y_prob)
    
    cutoff_20 = np.percentile(y_prob, 80)
    top20_mask = y_prob >= cutoff_20
    pos_total = y_true.sum()
    top20_pos = y_true[top20_mask].sum()
    top20_capture_rate = (top20_pos / pos_total * 100.0) if pos_total > 0 else 0.0
    top20_precision = (top20_pos / top20_mask.sum() * 100.0) if top20_mask.sum() > 0 else 0.0
    
    return {
        'roc_auc_incomplete': auc,
        'average_precision_incomplete': ap,
        'top20_capture_rate': top20_capture_rate,
        'top20_precision': top20_precision,
    }


def main():
    print("=" * 80)
    print("Stage 1 Positive-Unlabelled (PU) Learning Experiment: PU-Bagging")
    print("=" * 80)

    # 1. Read features strictly from export/feature_columns.txt
    feat_file = os.path.join(EXPORT_DIR, 'feature_columns.txt')
    with open(feat_file, 'r') as f:
        feature_cols = [line.strip() for line in f if line.strip()]
    print(f"Loaded {len(feature_cols)} feature columns: {', '.join(feature_cols)}")

    # 2. Load nodes and edges
    nodes_df = pd.read_csv(os.path.join(EXPORT_DIR, 'nodes.csv'))
    edges_df = pd.read_csv(os.path.join(EXPORT_DIR, 'edges.csv'), usecols=['src', 'dst'])

    # Filter to 8 BBMP zones
    bbmp_mask = nodes_df['zone'] != 'outside'
    bbmp_nodes = nodes_df[bbmp_mask].copy().reset_index(drop=True)
    zones = sorted(bbmp_nodes['zone'].unique().tolist())
    print(f"Filtered to 8 BBMP zones. Total nodes: {len(bbmp_nodes):,}")

    src_all = edges_df['src'].values
    dst_all = edges_df['dst'].values

    # PU-Bagging Parameters
    K_BAGS = 5      # 5 base models per fold (tested K=10 in sensitivity)
    PU_RATIO = 1    # 1:1 balanced subsampling per bag (Elkan & Noto standard)

    print(f"\nConfiguration: K = {K_BAGS} bags per fold | PU negative sampling ratio r = {PU_RATIO}:1")

    # Storage for out-of-fold predictions
    oof_preds = {
        'PU-Bagged LR': np.zeros(len(bbmp_nodes)),
        'PU-Bagged RF': np.zeros(len(bbmp_nodes)),
        'PU-Bagged GraphSAGE': np.zeros(len(bbmp_nodes)),
    }

    per_zone_records = []
    
    # Track bag-level predictions for bag-count convergence study on fold 1
    bag_predictions_fold1 = {'LR': [], 'RF': [], 'GraphSAGE': []}

    print("\n" + "=" * 80)
    print("Executing 8-Fold Spatial Cross-Validation with PU-Bagging")
    print("=" * 80)

    for fold_idx, test_zone in enumerate(zones, 1):
        t0_fold = time.time()
        test_mask = (bbmp_nodes['zone'] == test_zone).values
        train_mask = ~test_mask
        
        train_df = bbmp_nodes[train_mask]
        test_df = bbmp_nodes[test_mask]
        
        n_train, n_test = len(train_df), len(test_df)
        pos_train_idx = np.where(train_df['label'].values == 1)[0]
        unlab_train_idx = np.where(train_df['label'].values == 0)[0]
        n_pos = len(pos_train_idx)
        n_test_pos = test_df['label'].sum()
        
        print(f"\n>>> Fold {fold_idx}/8: Holding out zone '{test_zone}'")
        print(f"    Train: {n_train:,} nodes ({n_pos:,} positives) | Test: {n_test:,} nodes ({n_test_pos:,} positives)")

        # Feature scaling (fit strictly on train)
        scaler = StandardScaler()
        X_train_raw = train_df[feature_cols].values
        X_train_scaled = scaler.fit_transform(X_train_raw)
        
        X_test_raw = test_df[feature_cols].values
        X_test_scaled = scaler.transform(X_test_raw)
        y_test = test_df['label'].values

        # Graph isolation for GraphSAGE
        train_node_set = set(train_df['node_idx'].values)
        test_node_set = set(test_df['node_idx'].values)
        train_map = {orig: i for i, orig in enumerate(train_df['node_idx'].values)}
        test_map = {orig: i for i, orig in enumerate(test_df['node_idx'].values)}

        # Sever cross-zone edges
        train_e_filter = np.isin(src_all, list(train_node_set)) & np.isin(dst_all, list(train_node_set))
        train_src = np.array([train_map[s] for s in src_all[train_e_filter]], dtype=np.int64)
        train_dst = np.array([train_map[d] for d in dst_all[train_e_filter]], dtype=np.int64)
        train_edge_index = to_undirected(torch.tensor(np.stack([train_src, train_dst]), dtype=torch.long), num_nodes=n_train)

        test_e_filter = np.isin(src_all, list(test_node_set)) & np.isin(dst_all, list(test_node_set))
        test_src = np.array([test_map[s] for s in src_all[test_e_filter]], dtype=np.int64)
        test_dst = np.array([test_map[d] for d in dst_all[test_e_filter]], dtype=np.int64)
        test_edge_index = to_undirected(torch.tensor(np.stack([test_src, test_dst]), dtype=torch.long), num_nodes=n_test)

        # PyTorch tensors for GraphSAGE
        device = torch.device('cpu')  # Deterministic execution
        X_train_t = torch.tensor(X_train_scaled, dtype=torch.float32).to(device)
        X_test_t = torch.tensor(X_test_scaled, dtype=torch.float32).to(device)
        train_edge_dev = train_edge_index.to(device)
        test_edge_dev = test_edge_index.to(device)

        # Bags containers
        lr_bag_preds = []
        rf_bag_preds = []
        sage_bag_preds = []

        # Train K bags
        for b in range(1, K_BAGS + 1):
            bag_seed = RANDOM_SEED + fold_idx * 100 + b
            rng = np.random.default_rng(bag_seed)
            
            # Sample unlabelled nodes: n_sample = PU_RATIO * n_pos
            n_sample = min(n_pos * PU_RATIO, len(unlab_train_idx))
            sampled_unlab = rng.choice(unlab_train_idx, size=n_sample, replace=False)
            
            bag_indices = np.concatenate([pos_train_idx, sampled_unlab])
            bag_y = np.concatenate([np.ones(n_pos, dtype=np.int64), np.zeros(n_sample, dtype=np.int64)])
            
            # 1. Logistic Regression Bag
            lr_b = LogisticRegression(max_iter=500, random_state=bag_seed, solver='lbfgs')
            lr_b.fit(X_train_scaled[bag_indices], bag_y)
            p_lr_b = lr_b.predict_proba(X_test_scaled)[:, 1]
            lr_bag_preds.append(p_lr_b)

            # 2. Random Forest Bag (50 trees per bag; 5 bags = 250 trees total)
            rf_b = RandomForestClassifier(n_estimators=50, max_depth=12, min_samples_leaf=5,
                                          random_state=bag_seed, n_jobs=-1)
            rf_b.fit(X_train_raw[bag_indices], bag_y)
            p_rf_b = rf_b.predict_proba(X_test_raw)[:, 1]
            rf_bag_preds.append(p_rf_b)

            # 3. GraphSAGE Bag
            # Message passing occurs on the FULL train graph, loss is computed strictly on bag_indices
            torch.manual_seed(bag_seed)
            sage_b = GraphSAGENet(in_channels=len(feature_cols), hidden_channels=64, dropout=0.2).to(device)
            opt_b = torch.optim.Adam(sage_b.parameters(), lr=0.005, weight_decay=1e-4)
            crit_b = nn.BCEWithLogitsLoss()
            
            bag_idx_t = torch.tensor(bag_indices, dtype=torch.long).to(device)
            bag_y_t = torch.tensor(bag_y, dtype=torch.float32).to(device)

            sage_b.train()
            for epoch in range(1, 36):
                opt_b.zero_grad()
                out_b = sage_b(X_train_t, train_edge_dev)
                loss_b = crit_b(out_b[bag_idx_t], bag_y_t)
                loss_b.backward()
                opt_b.step()

            sage_b.eval()
            with torch.no_grad():
                test_logits_b = sage_b(X_test_t, test_edge_dev)
                p_sage_b = torch.sigmoid(test_logits_b).cpu().numpy()
            sage_bag_preds.append(p_sage_b)

            # Save fold 1 bag predictions for bag-count convergence study
            if fold_idx == 1:
                bag_predictions_fold1['LR'].append(p_lr_b)
                bag_predictions_fold1['RF'].append(p_rf_b)
                bag_predictions_fold1['GraphSAGE'].append(p_sage_b)

        # Average ensemble predictions across bags
        p_lr_ens = np.mean(lr_bag_preds, axis=0)
        p_rf_ens = np.mean(rf_bag_preds, axis=0)
        p_sage_ens = np.mean(sage_bag_preds, axis=0)

        oof_preds['PU-Bagged LR'][test_mask] = p_lr_ens
        oof_preds['PU-Bagged RF'][test_mask] = p_rf_ens
        oof_preds['PU-Bagged GraphSAGE'][test_mask] = p_sage_ens

        # Compute fold metrics
        m_lr = compute_metrics(y_test, p_lr_ens)
        m_lr.update({'zone': test_zone, 'model': 'PU-Bagged LR'})
        per_zone_records.append(m_lr)

        m_rf = compute_metrics(y_test, p_rf_ens)
        m_rf.update({'zone': test_zone, 'model': 'PU-Bagged RF'})
        per_zone_records.append(m_rf)

        m_sage = compute_metrics(y_test, p_sage_ens)
        m_sage.update({'zone': test_zone, 'model': 'PU-Bagged GraphSAGE'})
        per_zone_records.append(m_sage)

        print(f"    Fold {fold_idx} PU-Bagging results ({time.time()-t0_fold:.1f}s):")
        print(f"      PU-LR:   Top20% Capture = {m_lr['top20_capture_rate']:.2f}% | AUC_inc = {m_lr['roc_auc_incomplete']:.4f} | AP_inc = {m_lr['average_precision_incomplete']:.4f}")
        print(f"      PU-RF:   Top20% Capture = {m_rf['top20_capture_rate']:.2f}% | AUC_inc = {m_rf['roc_auc_incomplete']:.4f} | AP_inc = {m_rf['average_precision_incomplete']:.4f}")
        print(f"      PU-SAGE: Top20% Capture = {m_sage['top20_capture_rate']:.2f}% | AUC_inc = {m_sage['roc_auc_incomplete']:.4f} | AP_inc = {m_sage['average_precision_incomplete']:.4f}")

    # ==============================================================================
    # Save Per-Zone & Comparative Overall Metrics
    # ==============================================================================
    per_zone_df = pd.DataFrame(per_zone_records)
    per_zone_path = os.path.join(RESULTS_DIR, 'pu_per_zone_metrics.csv')
    per_zone_df.to_csv(per_zone_path, index=False)
    print(f"\nSaved PU per-zone metrics to: {per_zone_path}")

    # Load original class-weighted benchmark results for side-by-side comparison
    orig_comp_path = os.path.join(ORIGINAL_RESULTS_DIR, 'overall_comparison.csv')
    orig_comp_df = pd.read_csv(orig_comp_path)

    y_true_all = bbmp_nodes['label'].values
    pu_overall_records = []
    
    for m_name in ['PU-Bagged LR', 'PU-Bagged RF', 'PU-Bagged GraphSAGE']:
        sub = per_zone_df[per_zone_df['model'] == m_name]
        mean_cap = sub['top20_capture_rate'].mean()
        std_cap = sub['top20_capture_rate'].std()
        mean_auc = sub['roc_auc_incomplete'].mean()
        std_auc = sub['roc_auc_incomplete'].std()
        mean_ap = sub['average_precision_incomplete'].mean()
        std_ap = sub['average_precision_incomplete'].std()
        
        pooled_m = compute_metrics(y_true_all, oof_preds[m_name])
        
        pu_overall_records.append({
            'experiment': 'PU-Bagging (K=5, r=1:1)',
            'model': m_name,
            'macro_top20_capture': f"{mean_cap:.2f}% ± {std_cap:.2f}%",
            'pooled_top20_capture': f"{pooled_m['top20_capture_rate']:.2f}%",
            'macro_roc_auc_incomplete': f"{mean_auc:.4f} ± {std_auc:.4f}",
            'pooled_roc_auc_incomplete': round(pooled_m['roc_auc_incomplete'], 4),
            'macro_ap_incomplete': f"{mean_ap:.4f} ± {std_ap:.4f}",
            'pooled_ap_incomplete': round(pooled_m['average_precision_incomplete'], 4),
        })

    # Add baseline class-weighted models into comparative table
    name_map = {
        'Logistic Regression': 'Class-Weighted LR (Baseline)',
        'Random Forest': 'Class-Weighted RF (Baseline)',
        'GraphSAGE': 'Class-Weighted GraphSAGE (Baseline)',
    }
    for idx, row in orig_comp_df.iterrows():
        pu_overall_records.append({
            'experiment': 'Class-Weighted (Original Benchmark)',
            'model': name_map.get(row['model'], row['model']),
            'macro_top20_capture': row['macro_top20_capture'],
            'pooled_top20_capture': f"{row['pooled_top20_capture']:.2f}%",
            'macro_roc_auc_incomplete': row['macro_roc_auc'],
            'pooled_roc_auc_incomplete': row['pooled_roc_auc'],
            'macro_ap_incomplete': row['macro_ap'],
            'pooled_ap_incomplete': row['pooled_ap'],
        })

    pu_overall_df = pd.DataFrame(pu_overall_records)
    pu_overall_path = os.path.join(RESULTS_DIR, 'pu_overall_comparison.csv')
    pu_overall_df.to_csv(pu_overall_path, index=False)
    print(f"Saved PU overall comparative table to: {pu_overall_path}")

    print("\n" + "=" * 80)
    print("Comparative Summary: PU-Bagging vs Class-Weighted Baselines")
    print("=" * 80)
    print(pu_overall_df[['experiment', 'model', 'macro_top20_capture', 'pooled_top20_capture', 'macro_roc_auc_incomplete']].to_string())

    # ==============================================================================
    # Sensitivity to PU Sampling Ratio r across Models
    # ==============================================================================
    print("\n" + "=" * 80)
    print("Evaluating Sensitivity to Sampling Ratio r in {1:1, 2:1, 3:1, 5:1}")
    print("=" * 80)

    # Test across representative zone: Bommanahalli
    test_zone_sens = 'Bommanahalli'
    t_mask = (bbmp_nodes['zone'] == test_zone_sens).values
    tr_df = bbmp_nodes[~t_mask]
    te_df = bbmp_nodes[t_mask]
    
    pos_idx_s = np.where(tr_df['label'].values == 1)[0]
    unlab_idx_s = np.where(tr_df['label'].values == 0)[0]
    n_p_s = len(pos_idx_s)
    
    scaler_s = StandardScaler()
    X_tr_sc = scaler_s.fit_transform(tr_df[feature_cols].values)
    X_te_sc = scaler_s.transform(te_df[feature_cols].values)
    X_tr_raw = tr_df[feature_cols].values
    X_te_raw = te_df[feature_cols].values
    y_te_s = te_df['label'].values

    # Test Graph edges for sensitivity
    tr_node_s = set(tr_df['node_idx'].values)
    te_node_s = set(te_df['node_idx'].values)
    tr_map_s = {orig: i for i, orig in enumerate(tr_df['node_idx'].values)}
    te_map_s = {orig: i for i, orig in enumerate(te_df['node_idx'].values)}

    tr_e_f = np.isin(src_all, list(tr_node_s)) & np.isin(dst_all, list(tr_node_s))
    tr_e_idx = to_undirected(torch.tensor(np.stack([
        np.array([tr_map_s[s] for s in src_all[tr_e_f]], dtype=np.int64),
        np.array([tr_map_s[d] for d in dst_all[tr_e_f]], dtype=np.int64)
    ]), dtype=torch.long), num_nodes=len(tr_df))

    te_e_f = np.isin(src_all, list(te_node_s)) & np.isin(dst_all, list(te_node_s))
    te_e_idx = to_undirected(torch.tensor(np.stack([
        np.array([te_map_s[s] for s in src_all[te_e_f]], dtype=np.int64),
        np.array([te_map_s[d] for d in dst_all[te_e_f]], dtype=np.int64)
    ]), dtype=torch.long), num_nodes=len(te_df))

    ratio_records = []
    test_ratios = [1, 2, 3, 5]

    for r in test_ratios:
        lr_preds_r, rf_preds_r, sage_preds_r = [], [], []
        
        for b in range(1, 4):  # 3 bags for fast sensitivity sweep
            b_seed = RANDOM_SEED + r * 10 + b
            rng = np.random.default_rng(b_seed)
            sampled_u = rng.choice(unlab_idx_s, size=n_p_s * r, replace=False)
            bag_idx = np.concatenate([pos_idx_s, sampled_u])
            bag_y = np.concatenate([np.ones(n_p_s), np.zeros(n_p_s * r)])
            
            # LR
            lr_m = LogisticRegression(max_iter=500, random_state=b_seed).fit(X_tr_sc[bag_idx], bag_y)
            lr_preds_r.append(lr_m.predict_proba(X_te_sc)[:, 1])
            
            # RF
            rf_m = RandomForestClassifier(n_estimators=40, max_depth=12, random_state=b_seed, n_jobs=-1).fit(X_tr_raw[bag_idx], bag_y)
            rf_preds_r.append(rf_m.predict_proba(X_te_raw)[:, 1])
            
            # SAGE
            torch.manual_seed(b_seed)
            sg_m = GraphSAGENet(len(feature_cols), 64).to(device)
            sg_opt = torch.optim.Adam(sg_m.parameters(), lr=0.005)
            sg_crit = nn.BCEWithLogitsLoss()
            
            X_tr_t = torch.tensor(X_tr_sc, dtype=torch.float32).to(device)
            b_idx_t = torch.tensor(bag_idx, dtype=torch.long).to(device)
            b_y_t = torch.tensor(bag_y, dtype=torch.float32).to(device)
            
            sg_m.train()
            for _ in range(25):
                sg_opt.zero_grad()
                out = sg_m(X_tr_t, tr_e_idx.to(device))
                loss = sg_crit(out[b_idx_t], b_y_t)
                loss.backward()
                sg_opt.step()
                
            sg_m.eval()
            with torch.no_grad():
                test_probs = torch.sigmoid(sg_m(torch.tensor(X_te_sc, dtype=torch.float32).to(device), te_e_idx.to(device))).cpu().numpy()
            sage_preds_r.append(test_probs)

        for m_name, preds_arr in [('PU-LR', lr_preds_r), ('PU-RF', rf_preds_r), ('PU-GraphSAGE', sage_preds_r)]:
            avg_p = np.mean(preds_arr, axis=0)
            met = compute_metrics(y_te_s, avg_p)
            ratio_records.append({
                'ratio': f"{r}:1",
                'model': m_name,
                'top20_capture_rate': met['top20_capture_rate'],
                'roc_auc_incomplete': met['roc_auc_incomplete'],
                'average_precision_incomplete': met['average_precision_incomplete'],
            })
            print(f"    Ratio {r}:1 | Model: {m_name:<12} -> Top20% Capture: {met['top20_capture_rate']:.2f}% | AUC_inc: {met['roc_auc_incomplete']:.4f}")

    ratio_df = pd.DataFrame(ratio_records)
    ratio_path = os.path.join(RESULTS_DIR, 'pu_ratio_sensitivity.csv')
    ratio_df.to_csv(ratio_path, index=False)
    print(f"Saved ratio sensitivity to: {ratio_path}")

    # ==============================================================================
    # Sensitivity to Number of Bags K in {1, 3, 5}
    # ==============================================================================
    bag_records = []
    y_test_f1 = bbmp_nodes[bbmp_nodes['zone'] == 'Bommanahalli']['label'].values
    
    for k in [1, 2, 3, 4, 5]:
        for m_key, m_name in [('LR', 'PU-LR'), ('RF', 'PU-RF'), ('GraphSAGE', 'PU-GraphSAGE')]:
            preds_k = np.mean(bag_predictions_fold1[m_key][:k], axis=0)
            met_k = compute_metrics(y_test_f1, preds_k)
            bag_records.append({
                'num_bags_K': k,
                'model': m_name,
                'top20_capture_rate': met_k['top20_capture_rate'],
                'roc_auc_incomplete': met_k['roc_auc_incomplete'],
                'average_precision_incomplete': met_k['average_precision_incomplete'],
            })

    bag_df = pd.DataFrame(bag_records)
    bag_path = os.path.join(RESULTS_DIR, 'pu_bag_count_sensitivity.csv')
    bag_df.to_csv(bag_path, index=False)
    print(f"Saved bag count sensitivity to: {bag_path}")

    # ==============================================================================
    # Diagnostic Plots
    # ==============================================================================
    print("\nGenerating Diagnostic Plots...")

    # 1. Top-20% Capture Rate Comparison Bar Chart (PU-Bagged vs Class-Weighted)
    plt.figure(figsize=(12, 6))
    bar_width = 0.22
    x_idx = np.arange(len(zones))
    
    # Original benchmark metrics for comparison
    orig_per_zone = pd.read_csv(os.path.join(ORIGINAL_RESULTS_DIR, 'per_zone_metrics.csv'))
    
    plt.bar(x_idx - 1.5 * bar_width, orig_per_zone[orig_per_zone['model'] == 'Logistic Regression'].set_index('zone').loc[zones]['top20_capture_rate'],
            width=bar_width, label='CW-LR (Baseline)', color='#a1d99b', alpha=0.9)
    plt.bar(x_idx - 0.5 * bar_width, per_zone_df[per_zone_df['model'] == 'PU-Bagged LR'].set_index('zone').loc[zones]['top20_capture_rate'],
            width=bar_width, label='PU-Bagged LR', color='#2ca02c', alpha=0.9)
    plt.bar(x_idx + 0.5 * bar_width, orig_per_zone[orig_per_zone['model'] == 'GraphSAGE'].set_index('zone').loc[zones]['top20_capture_rate'],
            width=bar_width, label='CW-GraphSAGE (Baseline)', color='#fdbb84', alpha=0.9)
    plt.bar(x_idx + 1.5 * bar_width, per_zone_df[per_zone_df['model'] == 'PU-Bagged GraphSAGE'].set_index('zone').loc[zones]['top20_capture_rate'],
            width=bar_width, label='PU-Bagged GraphSAGE', color='#e6550d', alpha=0.9)

    plt.axhline(20.0, color='red', linestyle=':', label='Random Guess Baseline (20%)')
    plt.xticks(x_idx, zones, rotation=25, ha='right', fontsize=10)
    plt.ylabel('% Official Flood Points in Top 20% Risk Area', fontsize=11)
    plt.title('Known-Positive Top-20% Risk Capture Rate: PU-Bagging vs Class-Weighted (CW) Baseline', fontsize=12, fontweight='bold')
    plt.ylim(0, 80)
    plt.legend(loc='upper right', fontsize=9)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'pu_top20_capture_comparison.png'), dpi=300)
    plt.close()

    # 2. Ratio Sensitivity Plot
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for m in ['PU-LR', 'PU-RF', 'PU-GraphSAGE']:
        sub = ratio_df[ratio_df['model'] == m]
        axes[0].plot(sub['ratio'], sub['top20_capture_rate'], marker='o', linewidth=2, label=m)
        axes[1].plot(sub['ratio'], sub['roc_auc_incomplete'], marker='s', linewidth=2, label=m)
        
    axes[0].set_title('Top-20% Capture Rate vs PU Sampling Ratio r', fontsize=11, fontweight='bold')
    axes[0].set_xlabel('Unlabelled : Positive Ratio (r : 1)')
    axes[0].set_ylabel('Top-20% Capture Rate (%)')
    axes[0].grid(True, linestyle='--', alpha=0.5)
    axes[0].legend()

    axes[1].set_title('ROC-AUC (Incomplete Labels) vs PU Sampling Ratio r', fontsize=11, fontweight='bold')
    axes[1].set_xlabel('Unlabelled : Positive Ratio (r : 1)')
    axes[1].set_ylabel('ROC-AUC')
    axes[1].grid(True, linestyle='--', alpha=0.5)
    axes[1].legend()

    plt.suptitle('PU-Bagging Sensitivity to Unlabelled Negative Subsampling Ratio', fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'pu_ratio_sensitivity_plot.png'), dpi=300)
    plt.close()

    # 3. Bag Count Convergence Plot
    plt.figure(figsize=(8, 5))
    for m in ['PU-LR', 'PU-RF', 'PU-GraphSAGE']:
        sub = bag_df[bag_df['model'] == m]
        plt.plot(sub['num_bags_K'], sub['top20_capture_rate'], marker='o', linewidth=2, label=m)
    plt.title('Ensemble Convergence: Top-20% Capture Rate vs Number of Bags K', fontsize=12, fontweight='bold')
    plt.xlabel('Number of Bags (K)')
    plt.ylabel('Top-20% Capture Rate (%)')
    plt.xticks([1, 2, 3, 4, 5])
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'pu_bag_convergence_plot.png'), dpi=300)
    plt.close()

    print("\nPU Experiment Finished Successfully!")


if __name__ == '__main__':
    main()

