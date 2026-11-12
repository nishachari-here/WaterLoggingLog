#!/usr/bin/env python3
"""
Stage 1 Model Training & Spatial Cross-Validation: Bengaluru Waterlogging Prediction
===================================================================================
Models compared:
  1. Logistic Regression (L2 regularized, standard scaled)
  2. Random Forest (100 trees, max_depth=12, balanced weighting)
  3. GraphSAGE (2-layer PyTorch Geometric GNN with mean aggregation)

Validation:
  - 8-fold spatial leave-one-zone-out cross-validation across the 8 BBMP zones.
  - zone="outside" is strictly excluded from all training and test folds.
  - Zero leakage: Cross-zone edges touching the held-out test zone are removed during training.
  - Strict inductive evaluation on the held-out zone.
  - Positive-Unlabelled (PU) learning treatment with sensitivity analysis across sampling ratios.

All 10 features are loaded directly from export/feature_columns.txt.
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
    precision_score,
    recall_score,
    f1_score,
    roc_curve,
    precision_recall_curve,
)

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv
from torch_geometric.utils import to_undirected

# Set random seeds for absolute reproducibility
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(RANDOM_SEED)

# Paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
EXPORT_DIR = os.path.join(REPO_ROOT, 'export')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
CHECKPOINTS_DIR = os.path.join(BASE_DIR, 'checkpoints')

os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(CHECKPOINTS_DIR, exist_ok=True)


# ==============================================================================
# 1. PyTorch Geometric GraphSAGE Definition
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
        out = self.fc(h).squeeze(-1)
        return out


def compute_metrics(y_true, y_prob, threshold=0.5):
    """
    Computes classification and spatial disaster management metrics:
      - ROC-AUC
      - Average Precision (PR-AUC)
      - Precision at threshold
      - Recall at threshold
      - F1 at threshold
      - Top-20% Risk Area Capture Rate (% of positives in top 20% predicted scores)
      - Top-20% Precision
    """
    auc = roc_auc_score(y_true, y_prob)
    ap = average_precision_score(y_true, y_prob)
    
    y_pred = (y_prob >= threshold).astype(int)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    
    # Top 20% predicted risk area metric
    cutoff_20 = np.percentile(y_prob, 80)
    top20_mask = y_prob >= cutoff_20
    pos_total = y_true.sum()
    top20_pos = y_true[top20_mask].sum()
    top20_capture_rate = (top20_pos / pos_total * 100.0) if pos_total > 0 else 0.0
    top20_precision = (top20_pos / top20_mask.sum() * 100.0) if top20_mask.sum() > 0 else 0.0
    
    return {
        'roc_auc': auc,
        'average_precision': ap,
        'precision': prec,
        'recall': rec,
        'f1_score': f1,
        'top20_capture_rate': top20_capture_rate,
        'top20_precision': top20_precision,
    }


# ==============================================================================
# 2. Main Training & Spatial Validation Routine
# ==============================================================================
def main():
    print("=" * 80)
    print("Bengaluru Waterlogging Prediction — Stage 1 Model Training")
    print("=" * 80)

    # 1. Read features strictly from export/feature_columns.txt
    feat_file = os.path.join(EXPORT_DIR, 'feature_columns.txt')
    with open(feat_file, 'r') as f:
        feature_cols = [line.strip() for line in f if line.strip()]
    print(f"[1/7] Loaded {len(feature_cols)} feature columns from {feat_file}:")
    for idx, col in enumerate(feature_cols, 1):
        print(f"      {idx:2d}. {col}")

    # 2. Read exported nodes and edges
    print(f"\n[2/7] Loading node and edge data...")
    nodes_df = pd.read_csv(os.path.join(EXPORT_DIR, 'nodes.csv'))
    edges_df = pd.read_csv(os.path.join(EXPORT_DIR, 'edges.csv'), usecols=['src', 'dst'])
    print(f"      Total raw nodes: {len(nodes_df):,}")
    print(f"      Total raw edges: {len(edges_df):,}")

    # Exclude zone="outside" from analysis
    bbmp_mask = nodes_df['zone'] != 'outside'
    bbmp_nodes = nodes_df[bbmp_mask].copy().reset_index(drop=True)
    zones = sorted(bbmp_nodes['zone'].unique().tolist())
    print(f"\n      Filtered to 8 BBMP zones (excluded {len(nodes_df) - len(bbmp_nodes):,} 'outside' nodes)")
    print(f"      Active BBMP nodes: {len(bbmp_nodes):,}")
    print(f"      Zones ({len(zones)}): {', '.join(zones)}")
    
    zone_stats = bbmp_nodes.groupby('zone')['label'].agg(['count', 'sum'])
    zone_stats.columns = ['total_nodes', 'flood_positives']
    zone_stats['positive_pct'] = (zone_stats['flood_positives'] / zone_stats['total_nodes']) * 100
    print("\n      Zone Breakdown:")
    print(zone_stats.to_string())

    # Check for NaN in features
    nan_counts = bbmp_nodes[feature_cols].isna().sum()
    if nan_counts.any():
        raise ValueError(f"Found NaN in features: {nan_counts[nan_counts > 0].to_dict()}")

    # Raw edge endpoints
    src_all = edges_df['src'].values
    dst_all = edges_df['dst'].values

    # Storage for out-of-fold predictions and per-zone metrics
    oof_predictions = {
        'Logistic Regression': np.zeros(len(bbmp_nodes)),
        'Random Forest': np.zeros(len(bbmp_nodes)),
        'GraphSAGE': np.zeros(len(bbmp_nodes)),
    }
    
    per_zone_records = []
    trained_models = {'LR': {}, 'RF': {}, 'GraphSAGE': {}, 'Scaler': {}}
    rf_feature_importances = []
    lr_coefficients = []

    print("\n" + "=" * 80)
    print("[3/7] Running 8-Fold Spatial Cross-Validation (Leave-One-Zone-Out)")
    print("=" * 80)

    for fold_idx, test_zone in enumerate(zones, 1):
        t0_fold = time.time()
        print(f"\n>>> Fold {fold_idx}/8: Holding out zone '{test_zone}'")
        
        test_mask = (bbmp_nodes['zone'] == test_zone).values
        train_mask = ~test_mask
        
        train_df = bbmp_nodes[train_mask]
        test_df = bbmp_nodes[test_mask]
        
        n_train = len(train_df)
        n_test = len(test_df)
        n_train_pos = train_df['label'].sum()
        n_test_pos = test_df['label'].sum()
        print(f"    Train nodes: {n_train:,} ({n_train_pos:,} positives, {n_train_pos/n_train*100:.2f}%)")
        print(f"    Test nodes:  {n_test:,} ({n_test_pos:,} positives, {n_test_pos/n_test*100:.2f}%)")

        # ----------------------------------------------------------------------
        # Feature Scaling
        # ----------------------------------------------------------------------
        scaler = StandardScaler()
        X_train_raw = train_df[feature_cols].values
        y_train = train_df['label'].values
        
        X_test_raw = test_df[feature_cols].values
        y_test = test_df['label'].values
        
        X_train_scaled = scaler.fit_transform(X_train_raw)
        X_test_scaled = scaler.transform(X_test_raw)
        
        trained_models['Scaler'][test_zone] = scaler
        joblib.dump(scaler, os.path.join(CHECKPOINTS_DIR, f'scaler_{test_zone}.joblib'))

        # ----------------------------------------------------------------------
        # Graph Construction & Leakage Elimination for GraphSAGE
        # ----------------------------------------------------------------------
        train_node_idx_set = set(train_df['node_idx'].values)
        test_node_idx_set = set(test_df['node_idx'].values)
        
        train_map = {orig: i for i, orig in enumerate(train_df['node_idx'].values)}
        test_map = {orig: i for i, orig in enumerate(test_df['node_idx'].values)}
        
        # Strictly isolate training edges: both src and dst must belong to train_node_idx_set
        train_edge_filter = np.isin(src_all, list(train_node_idx_set)) & np.isin(dst_all, list(train_node_idx_set))
        train_src = np.array([train_map[s] for s in src_all[train_edge_filter]], dtype=np.int64)
        train_dst = np.array([train_map[d] for d in dst_all[train_edge_filter]], dtype=np.int64)
        train_edge_index = torch.tensor(np.stack([train_src, train_dst]), dtype=torch.long)
        train_edge_index = to_undirected(train_edge_index, num_nodes=n_train)
        
        # Test edges: strictly within test zone (inductive spatial evaluation)
        test_edge_filter = np.isin(src_all, list(test_node_idx_set)) & np.isin(dst_all, list(test_node_idx_set))
        test_src = np.array([test_map[s] for s in src_all[test_edge_filter]], dtype=np.int64)
        test_dst = np.array([test_map[d] for d in dst_all[test_edge_filter]], dtype=np.int64)
        test_edge_index = torch.tensor(np.stack([test_src, test_dst]), dtype=torch.long)
        test_edge_index = to_undirected(test_edge_index, num_nodes=n_test)
        
        cross_edges_count = ((np.isin(src_all, list(train_node_idx_set)) & np.isin(dst_all, list(test_node_idx_set))) |
                             (np.isin(src_all, list(test_node_idx_set)) & np.isin(dst_all, list(train_node_idx_set)))).sum()
        print(f"    Graph isolation: {cross_edges_count} boundary-crossing edges severed to prevent graph leakage.")
        print(f"    Train subgraph edges: {train_edge_index.size(1):,}; Test subgraph edges: {test_edge_index.size(1):,}")

        # ----------------------------------------------------------------------
        # Model 1: Logistic Regression
        # ----------------------------------------------------------------------
        t0_m = time.time()
        lr = LogisticRegression(
            max_iter=1000,
            class_weight='balanced',
            random_state=RANDOM_SEED,
            solver='lbfgs'
        )
        lr.fit(X_train_scaled, y_train)
        lr_probs = lr.predict_proba(X_test_scaled)[:, 1]
        oof_predictions['Logistic Regression'][test_mask] = lr_probs
        lr_metrics = compute_metrics(y_test, lr_probs)
        lr_metrics.update({'zone': test_zone, 'model': 'Logistic Regression'})
        per_zone_records.append(lr_metrics)
        lr_coefficients.append(lr.coef_[0])
        trained_models['LR'][test_zone] = lr
        joblib.dump(lr, os.path.join(CHECKPOINTS_DIR, f'lr_{test_zone}.joblib'))
        print(f"    [LR] AUC: {lr_metrics['roc_auc']:.4f} | AP: {lr_metrics['average_precision']:.4f} | "
              f"Top-20% Capture: {lr_metrics['top20_capture_rate']:.2f}% ({time.time()-t0_m:.2f}s)")

        # ----------------------------------------------------------------------
        # Model 2: Random Forest
        # ----------------------------------------------------------------------
        t0_m = time.time()
        rf = RandomForestClassifier(
            n_estimators=100,
            max_depth=12,
            min_samples_leaf=10,
            class_weight='balanced',
            random_state=RANDOM_SEED,
            n_jobs=-1
        )
        rf.fit(X_train_raw, y_train)
        rf_probs = rf.predict_proba(X_test_raw)[:, 1]
        oof_predictions['Random Forest'][test_mask] = rf_probs
        rf_metrics = compute_metrics(y_test, rf_probs)
        rf_metrics.update({'zone': test_zone, 'model': 'Random Forest'})
        per_zone_records.append(rf_metrics)
        rf_feature_importances.append(rf.feature_importances_)
        trained_models['RF'][test_zone] = rf
        joblib.dump(rf, os.path.join(CHECKPOINTS_DIR, f'rf_{test_zone}.joblib'))
        print(f"    [RF] AUC: {rf_metrics['roc_auc']:.4f} | AP: {rf_metrics['average_precision']:.4f} | "
              f"Top-20% Capture: {rf_metrics['top20_capture_rate']:.2f}% ({time.time()-t0_m:.2f}s)")

        # ----------------------------------------------------------------------
        # Model 3: GraphSAGE GNN
        # ----------------------------------------------------------------------
        t0_m = time.time()
        X_train_t = torch.tensor(X_train_scaled, dtype=torch.float32)
        y_train_t = torch.tensor(y_train, dtype=torch.float32)
        X_test_t = torch.tensor(X_test_scaled, dtype=torch.float32)
        
        # Device selection: MPS / CUDA / CPU
        device = torch.device('cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu'))
        # Note: on some Mac PyTorch MPS combinations SAGEConv can fall back or be slower, CPU is verified 0.4s
        device = torch.device('cpu')  # Rock-solid deterministic execution
        
        sage = GraphSAGENet(in_channels=len(feature_cols), hidden_channels=64, dropout=0.2).to(device)
        optimizer = torch.optim.Adam(sage.parameters(), lr=0.005, weight_decay=1e-4)
        
        pos_weight_val = (len(y_train) - n_train_pos) / max(n_train_pos, 1)
        pos_weight = torch.tensor([pos_weight_val], dtype=torch.float32).to(device)
        criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        
        X_train_dev = X_train_t.to(device)
        y_train_dev = y_train_t.to(device)
        train_edge_dev = train_edge_index.to(device)
        
        # 45 epochs training
        sage.train()
        for epoch in range(1, 46):
            optimizer.zero_grad()
            logits = sage(X_train_dev, train_edge_dev)
            loss = criterion(logits, y_train_dev)
            loss.backward()
            optimizer.step()
            
        sage.eval()
        with torch.no_grad():
            test_logits = sage(X_test_t.to(device), test_edge_index.to(device))
            sage_probs = torch.sigmoid(test_logits).cpu().numpy()
            
        oof_predictions['GraphSAGE'][test_mask] = sage_probs
        sage_metrics = compute_metrics(y_test, sage_probs)
        sage_metrics.update({'zone': test_zone, 'model': 'GraphSAGE'})
        per_zone_records.append(sage_metrics)
        trained_models['GraphSAGE'][test_zone] = sage
        torch.save(sage.state_dict(), os.path.join(CHECKPOINTS_DIR, f'graphsage_{test_zone}.pt'))
        print(f"    [SAGE] AUC: {sage_metrics['roc_auc']:.4f} | AP: {sage_metrics['average_precision']:.4f} | "
              f"Top-20% Capture: {sage_metrics['top20_capture_rate']:.2f}% ({time.time()-t0_m:.2f}s)")
        print(f"    Fold {fold_idx} completed in {time.time()-t0_fold:.2f}s")

    # ==============================================================================
    # 4. Save Per-Zone & Overall Summary Metrics
    # ==============================================================================
    print("\n" + "=" * 80)
    print("[4/7] Generating Per-Zone & Overall Comparison Tables")
    print("=" * 80)

    per_zone_df = pd.DataFrame(per_zone_records)
    metric_cols = ['roc_auc', 'average_precision', 'precision', 'recall', 'f1_score', 'top20_capture_rate', 'top20_precision']
    
    # Reorder columns
    ordered_cols = ['zone', 'model'] + metric_cols
    per_zone_df = per_zone_df[ordered_cols]
    per_zone_path = os.path.join(RESULTS_DIR, 'per_zone_metrics.csv')
    per_zone_df.to_csv(per_zone_path, index=False)
    print(f"Saved per-zone metrics to: {per_zone_path}")

    # Compute Macro-Averages and Pooled (Micro-Average) Metrics
    y_true_all = bbmp_nodes['label'].values
    overall_records = []
    
    for model_name in ['Logistic Regression', 'Random Forest', 'GraphSAGE']:
        model_zone_df = per_zone_df[per_zone_df['model'] == model_name]
        
        # Macro (mean +/- std across the 8 zones)
        macro_mean = model_zone_df[metric_cols].mean()
        macro_std = model_zone_df[metric_cols].std()
        
        # Pooled (evaluated across all 157,533 out-of-fold predictions)
        pooled_probs = oof_predictions[model_name]
        pooled_metrics = compute_metrics(y_true_all, pooled_probs)
        
        rec = {
            'model': model_name,
            'macro_roc_auc': f"{macro_mean['roc_auc']:.4f} ± {macro_std['roc_auc']:.4f}",
            'pooled_roc_auc': round(pooled_metrics['roc_auc'], 4),
            'macro_ap': f"{macro_mean['average_precision']:.4f} ± {macro_std['average_precision']:.4f}",
            'pooled_ap': round(pooled_metrics['average_precision'], 4),
            'macro_top20_capture': f"{macro_mean['top20_capture_rate']:.2f}% ± {macro_std['top20_capture_rate']:.2f}%",
            'pooled_top20_capture': round(pooled_metrics['top20_capture_rate'], 2),
            'macro_top20_precision': f"{macro_mean['top20_precision']:.2f}% ± {macro_std['top20_precision']:.2f}%",
            'pooled_top20_precision': round(pooled_metrics['top20_precision'], 2),
            'macro_precision': round(macro_mean['precision'], 4),
            'macro_recall': round(macro_mean['recall'], 4),
            'macro_f1': round(macro_mean['f1_score'], 4),
        }
        overall_records.append(rec)

    overall_df = pd.DataFrame(overall_records)
    overall_path = os.path.join(RESULTS_DIR, 'overall_comparison.csv')
    overall_df.to_csv(overall_path, index=False)
    print(f"Saved overall comparison to: {overall_path}")
    print("\nOverall Spatial Cross-Validation Performance:")
    print(overall_df[['model', 'macro_roc_auc', 'macro_ap', 'macro_top20_capture', 'pooled_top20_capture']].to_string())

    # ==============================================================================
    # 5. Feature Importance Analysis for Classical Models
    # ==============================================================================
    print("\n" + "=" * 80)
    print("[5/7] Computing Classical Model Feature Importances")
    print("=" * 80)

    rf_imp_mean = np.mean(rf_feature_importances, axis=0)
    rf_imp_std = np.std(rf_feature_importances, axis=0)
    
    lr_coef_mean = np.mean(lr_coefficients, axis=0)
    lr_coef_std = np.std(lr_coefficients, axis=0)
    
    feat_imp_df = pd.DataFrame({
        'feature': feature_cols,
        'rf_importance_mean': rf_imp_mean,
        'rf_importance_std': rf_imp_std,
        'lr_coef_mean': lr_coef_mean,
        'lr_coef_std': lr_coef_std,
        'lr_odds_ratio': np.exp(lr_coef_mean),
    }).sort_values('rf_importance_mean', ascending=False).reset_index(drop=True)
    
    feat_imp_path = os.path.join(RESULTS_DIR, 'feature_importance.csv')
    feat_imp_df.to_csv(feat_imp_path, index=False)
    print(f"Saved feature importance table to: {feat_imp_path}")
    print("\nFeature Ranking:")
    print(feat_imp_df.to_string())

    # Plot Feature Importance
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Random Forest
    rf_sorted = feat_imp_df.sort_values('rf_importance_mean', ascending=True)
    axes[0].barh(rf_sorted['feature'], rf_sorted['rf_importance_mean'], xerr=rf_sorted['rf_importance_std'],
                 color='#1f77b4', alpha=0.85, capsize=4)
    axes[0].set_title('Random Forest Feature Importance (MDI ± 1 SD)', fontsize=12, fontweight='bold')
    axes[0].set_xlabel('Gini Importance')
    axes[0].grid(axis='x', linestyle='--', alpha=0.5)

    # Logistic Regression
    lr_sorted = feat_imp_df.sort_values('lr_coef_mean', ascending=True)
    colors = ['#d62728' if c < 0 else '#2ca02c' for c in lr_sorted['lr_coef_mean']]
    axes[1].barh(lr_sorted['feature'], lr_sorted['lr_coef_mean'], xerr=lr_sorted['lr_coef_std'],
                 color=colors, alpha=0.85, capsize=4)
    axes[1].set_title('Logistic Regression Standardized Coefficients (± 1 SD)', fontsize=12, fontweight='bold')
    axes[1].set_xlabel('Standardized Log-Odds Coefficient')
    axes[1].axvline(0, color='black', linewidth=0.8, linestyle='--')
    axes[1].grid(axis='x', linestyle='--', alpha=0.5)

    plt.tight_layout()
    feat_fig_path = os.path.join(RESULTS_DIR, 'feature_importance.png')
    plt.savefig(feat_fig_path, dpi=300)
    plt.close()
    print(f"Saved feature importance plot to: {feat_fig_path}")

    # ==============================================================================
    # 6. Generate Evaluation Plots: ROC, Precision-Recall, and Top-20% Capture
    # ==============================================================================
    print("\n" + "=" * 80)
    print("[6/7] Generating ROC, Precision-Recall, and Zone Comparison Plots")
    print("=" * 80)

    # --- Plot A: ROC Curves ---
    plt.figure(figsize=(8, 7))
    model_colors = {'Logistic Regression': '#2ca02c', 'Random Forest': '#1f77b4', 'GraphSAGE': '#ff7f0e'}
    
    for model_name, color in model_colors.items():
        fpr, tpr, _ = roc_curve(y_true_all, oof_predictions[model_name])
        auc_val = roc_auc_score(y_true_all, oof_predictions[model_name])
        plt.plot(fpr, tpr, label=f"{model_name} (Pooled AUC = {auc_val:.3f})", color=color, linewidth=2)
        
    plt.plot([0, 1], [0, 1], 'k--', alpha=0.6, label='Random Chance (AUC = 0.500)')
    plt.xlabel('False Positive Rate (FPR)', fontsize=11)
    plt.ylabel('True Positive Rate (Sensitivity / Recall)', fontsize=11)
    plt.title('Out-of-Fold Spatial ROC Curves across 8 BBMP Zones', fontsize=13, fontweight='bold')
    plt.legend(loc='lower right', frameon=True, fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    roc_fig_path = os.path.join(RESULTS_DIR, 'roc_curves.png')
    plt.savefig(roc_fig_path, dpi=300)
    plt.close()
    print(f"Saved ROC curve plot to: {roc_fig_path}")

    # --- Plot B: Precision-Recall Curves ---
    plt.figure(figsize=(8, 7))
    base_rate = y_true_all.sum() / len(y_true_all)
    
    for model_name, color in model_colors.items():
        precision_vals, recall_vals, _ = precision_recall_curve(y_true_all, oof_predictions[model_name])
        ap_val = average_precision_score(y_true_all, oof_predictions[model_name])
        plt.plot(recall_vals, precision_vals, label=f"{model_name} (AP = {ap_val:.3f})", color=color, linewidth=2)
        
    plt.axhline(base_rate, color='k', linestyle='--', alpha=0.6, label=f'Base Prevalence ({base_rate*100:.1f}%)')
    plt.xlabel('Recall (Sensitivity)', fontsize=11)
    plt.ylabel('Precision (Positive Predictive Value)', fontsize=11)
    plt.title('Out-of-Fold Spatial Precision-Recall Curves across 8 BBMP Zones', fontsize=13, fontweight='bold')
    plt.legend(loc='upper right', frameon=True, fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    pr_fig_path = os.path.join(RESULTS_DIR, 'precision_recall_curves.png')
    plt.savefig(pr_fig_path, dpi=300)
    plt.close()
    print(f"Saved Precision-Recall curve plot to: {pr_fig_path}")

    # --- Plot C: Top-20% Risk Capture Rate by Zone ---
    plt.figure(figsize=(12, 6))
    zone_order = zones
    bar_width = 0.25
    x_indices = np.arange(len(zone_order))
    
    for idx, (model_name, color) in enumerate(model_colors.items()):
        sub_df = per_zone_df[per_zone_df['model'] == model_name].set_index('zone').loc[zone_order]
        plt.bar(x_indices + idx * bar_width, sub_df['top20_capture_rate'], width=bar_width,
                label=model_name, color=color, alpha=0.85)

    plt.axhline(20.0, color='red', linestyle=':', linewidth=1.5, label='Random Baseline (20%)')
    plt.xticks(x_indices + bar_width, zone_order, rotation=25, ha='right', fontsize=10)
    plt.ylabel('% Official Flood Points in Top 20% Risk Area', fontsize=11)
    plt.title('Disaster Planning Recall: Official Flood Points Captured in Top 20% Risk Area by Zone',
              fontsize=13, fontweight='bold')
    plt.ylim(0, 100)
    plt.legend(loc='upper right', frameon=True, fontsize=10)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    capture_fig_path = os.path.join(RESULTS_DIR, 'top20_capture_comparison.png')
    plt.savefig(capture_fig_path, dpi=300)
    plt.close()
    print(f"Saved Top-20% Capture comparison plot to: {capture_fig_path}")

    # ==============================================================================
    # 7. Positive-Unlabelled (PU) Sensitivity Analysis
    # ==============================================================================
    print("\n" + "=" * 80)
    print("[7/7] Conducting Positive-Unlabelled (PU) Learning Sensitivity Analysis")
    print("=" * 80)

    # We evaluate PU negative sampling ratios: 1:1, 2:1, 3:1, 5:1, 10:1, and All-Unlabelled
    # across 3 representative zones: Bommanahalli (Outer south), West (Core city), Mahadevapura (Tech corridor)
    eval_zones = ['Bommanahalli', 'West', 'Mahadevapura']
    ratios = [1, 2, 3, 5, 10, 'All']
    pu_records = []

    for zone in eval_zones:
        t_mask = (bbmp_nodes['zone'] == zone).values
        tr_df = bbmp_nodes[~t_mask]
        te_df = bbmp_nodes[t_mask]
        
        pos_indices = tr_df[tr_df['label'] == 1].index.values
        unlab_indices = tr_df[tr_df['label'] == 0].index.values
        n_pos = len(pos_indices)
        
        for r in ratios:
            rng = np.random.default_rng(RANDOM_SEED)
            if r == 'All':
                sub_train = tr_df
                weight = 'balanced'
            else:
                n_sample = min(n_pos * r, len(unlab_indices))
                chosen_unlab = rng.choice(unlab_indices, size=n_sample, replace=False)
                sub_idx = np.concatenate([pos_indices, chosen_unlab])
                sub_train = tr_df.loc[sub_idx]
                weight = None
                
            # Train Random Forest under this PU configuration
            clf = RandomForestClassifier(n_estimators=100, max_depth=12, class_weight=weight,
                                         random_state=RANDOM_SEED, n_jobs=-1)
            clf.fit(sub_train[feature_cols].values, sub_train['label'].values)
            probs = clf.predict_proba(te_df[feature_cols].values)[:, 1]
            
            m = compute_metrics(te_df['label'].values, probs)
            pu_records.append({
                'zone': zone,
                'pu_ratio': str(r),
                'roc_auc': m['roc_auc'],
                'average_precision': m['average_precision'],
                'top20_capture_rate': m['top20_capture_rate'],
                'top20_precision': m['top20_precision'],
            })
            print(f"    Zone: {zone:<13} | Ratio: {str(r):<4} | AUC: {m['roc_auc']:.4f} | "
                  f"AP: {m['average_precision']:.4f} | Top-20% Capture: {m['top20_capture_rate']:.2f}%")

    pu_df = pd.DataFrame(pu_records)
    pu_path = os.path.join(RESULTS_DIR, 'pu_sensitivity_analysis.csv')
    pu_df.to_csv(pu_path, index=False)
    print(f"Saved PU sensitivity analysis to: {pu_path}")

    # Plot PU Sensitivity Analysis
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    metrics_to_plot = [
        ('top20_capture_rate', 'Top-20% Risk Area Capture Rate (%)', axes[0]),
        ('roc_auc', 'Spatial ROC-AUC', axes[1]),
        ('average_precision', 'Average Precision (PR-AUC)', axes[2]),
    ]
    
    for metric_key, metric_title, ax in metrics_to_plot:
        for zone in eval_zones:
            sub = pu_df[pu_df['zone'] == zone]
            ax.plot(sub['pu_ratio'], sub[metric_key], marker='o', linewidth=2, label=zone)
        ax.set_title(metric_title, fontsize=11, fontweight='bold')
        ax.set_xlabel('Unlabelled-to-Positive Sampling Ratio (r : 1)')
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.legend(loc='best', fontsize=9)
        
    plt.suptitle('Positive-Unlabelled (PU) Sampling Sensitivity Analysis', fontsize=13, fontweight='bold')
    plt.tight_layout()
    pu_fig_path = os.path.join(RESULTS_DIR, 'pu_sensitivity.png')
    plt.savefig(pu_fig_path, dpi=300)
    plt.close()
    print(f"Saved PU sensitivity plot to: {pu_fig_path}")

    print("\n" + "=" * 80)
    print("STAGE 1 MODEL TRAINING COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == '__main__':
    main()
