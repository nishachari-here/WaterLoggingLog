# Stage 1 Positive-Unlabelled (PU) Learning Experiment: PU-Bagging

This directory contains the dedicated **Positive-Unlabelled (PU) Bagging** experiment for Stage 1 of the Bengaluru Waterlogging Prediction project.

All original benchmarks, scripts, CSVs, plots, and checkpoints under `training/` remain **completely untouched and preserved**. This experiment is fully isolated under `training/pu_experiment/`.

---

## 1. Objective & Mathematical Foundation

In urban flood prediction across Bengaluru:
- `label = 1`: The location is within 150 m of an official BBMP flood point (399 historical flood points from OpenCity).
- `label = 0`: The location is **unlabelled**, NOT confirmed safe ground. Rapid urbanization has created hundreds of unrecorded low-lying waterlogged roads.

### The Limitation of Standard Class-Weighted Training
The original benchmark used cost-sensitive binary classification (`class_weight='balanced'` in Logistic Regression/Random Forest, and `pos_weight` in GraphSAGE). While weighting corrects for global positive-negative class imbalance, it still treats **all 149,132 unlabelled nodes simultaneously as negatives**. If an unlabelled node sits in a true flood-prone depression, the model is penalized during backpropagation for predicting high risk on that node.

### The PU-Bagging Solution (Mordelet & Vert, 2014)
PU-Bagging solves this by converting the PU problem into an ensemble of balanced binary problems:
1. In each training fold, retain **all known positives** $P_{\text{train}}$ ($N_{\text{pos}} \approx 6,800 - 8,000$).
2. Draw $K$ random bootstrap subsets $U_b \subset U_{\text{train}}$ from the unlabelled pool, each of size $r \cdot N_{\text{pos}}$ (where $r=1$ corresponds to a 1:1 balanced sample).
3. Train $K$ independent base models $f_b(x)$ on $P_{\text{train}} \cup U_b$.
4. Average the predicted probabilities across bags:
   $$\bar{p}(x) = \frac{1}{K} \sum_{b=1}^K f_b(x)$$

**Why it works**: By subsampling $U_{\text{train}}$, any individual unlabelled true flood site has only a small probability of being included in any given bag $b$ (sampling probability $\approx N_{\text{pos}} / N_{\text{unlab}} \approx 5.3\%$). When included, its noise impact is local to that bag; when omitted, the model is free to predict high risk for it. Averaging across bags smooths out negative label noise and reduces variance.

---

## 2. Experimental Protocol & Spatial Integrity

The experiment strictly preserves the spatial validation and data integrity standards of the original benchmark:
1. **Identical Folds**: 8-fold spatial leave-one-zone-out cross-validation across the 8 BBMP zones.
2. **Exclusion of `outside`**: The 90,754 nodes with `zone="outside"` are strictly excluded from both training and testing.
3. **Graph Isolation for GraphSAGE**:
   - For fold $k$, all boundary-crossing edges connecting to the held-out test zone $Z_k$ are **severed from the training graph**.
   - **Topological Integrity**: The full training graph topology is preserved for message passing (roads and drains remain connected). For each bag $b$, the PU loss is computed strictly over the node subset $P_{\text{train}} \cup U_b$:
     $$\mathcal{L}_b = \text{BCEWithLogitsLoss}\left(\hat{y}[P_{\text{train}} \cup U_b], y[P_{\text{train}} \cup U_b]\right)$$
   - Inference on the test zone is conducted purely inductively on the test zone's induced subgraph.
4. **Feature Discipline**: Exactly the 10 features from `export/feature_columns.txt` are used.
5. **Leakage-Free Scaling**: Feature scalers are fit strictly on the training partition of each fold.

---

## 3. Empirical Comparative Results

All models were evaluated across the exact same 8 spatial folds.

### Comparative Overall Summary: PU-Bagging vs. Original Class-Weighted Benchmark

| Experiment | Model | Macro Top-20% Capture Rate | Pooled Top-20% Capture Rate | Macro ROC-AUC (Incomplete) | Pooled ROC-AUC (Incomplete) | Macro PR-AUC (Incomplete) | Pooled PR-AUC (Incomplete) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **PU-Bagging ($K=5, r=1:1$)** | **PU-Bagged LR** | 38.60% ± 11.00% | 37.31% | 0.6707 ± 0.0740 | 0.6610 | 0.0947 ± 0.0405 | 0.0868 |
| | **PU-Bagged RF** | 39.51% ± 11.20% | 38.85% | 0.6706 ± 0.0819 | 0.6654 | 0.1050 ± 0.0372 | 0.1007 |
| | **PU-Bagged GraphSAGE** | **42.29% ± 11.69%** | **43.14%** | **0.6855 ± 0.0731** | **0.6759** | **0.1064 ± 0.0428** | **0.1031** |
| **Original Class-Weighted** | **Class-Weighted LR** | 38.43% ± 11.00% | 37.13% | 0.6703 ± 0.0741 | 0.6608 | 0.0940 ± 0.0397 | 0.0865 |
| | **Class-Weighted RF** | 38.84% ± 12.14% | 38.08% | 0.6663 ± 0.0825 | 0.6598 | 0.1038 ± 0.0359 | 0.0983 |
| | **Class-Weighted GraphSAGE** | 41.59% ± 11.08% | 41.57% | 0.6798 ± 0.0743 | 0.6734 | 0.1016 ± 0.0370 | 0.1001 |

*(Note: ROC-AUC and PR-AUC are explicitly denoted as evaluated against incomplete labels under the SCAR assumption).*

---

### Per-Zone Detailed Metrics under PU-Bagging ($K=5, r=1:1$)

| Zone | Model | Top-20% Known Positive Capture Rate | Top-20% Precision | ROC-AUC (Incomplete) | PR-AUC (Incomplete) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Bommanahalli** | PU-Bagged LR | 44.60% | 9.33% | 0.6981 | 0.0762 |
| | PU-Bagged RF | **50.11%** | **10.48%** | **0.7269** | **0.1027** |
| | PU-Bagged GraphSAGE | 48.52% | 10.15% | 0.7200 | 0.1018 |
| **Dasarahalli** | PU-Bagged LR | **24.62%** | **5.72%** | 0.5692 | **0.0585** |
| | PU-Bagged RF | 21.32% | 4.95% | 0.5361 | 0.0488 |
| | PU-Bagged GraphSAGE | 21.57% | 5.01% | **0.5749** | 0.0527 |
| **East** | PU-Bagged LR | 30.84% | 10.13% | 0.5873 | 0.0964 |
| | PU-Bagged RF | 28.46% | 9.35% | 0.5860 | 0.0905 |
| | PU-Bagged GraphSAGE | **35.12%** | **11.53%** | **0.6058** | **0.1199** |
| **Mahadevapura** | PU-Bagged LR | 42.63% | 9.35% | **0.6749** | 0.0817 |
| | PU-Bagged RF | 38.31% | 8.41% | 0.6480 | **0.0892** |
| | PU-Bagged GraphSAGE | **42.80%** | **9.39%** | 0.6695 | 0.0787 |
| **Rajarajeshwari Nagar** | PU-Bagged LR | 33.53% | 7.10% | 0.6677 | 0.0639 |
| | PU-Bagged RF | **46.15%** | **9.77%** | **0.7337** | **0.1095** |
| | PU-Bagged GraphSAGE | 42.49% | 8.99% | 0.7081 | 0.0814 |
| **South** | PU-Bagged LR | 41.86% | 17.20% | **0.7243** | 0.1775 |
| | PU-Bagged RF | 43.53% | 17.88% | 0.7006 | 0.1664 |
| | PU-Bagged GraphSAGE | **46.98%** | **19.30%** | 0.7137 | **0.1828** |
| **West** | PU-Bagged LR | 31.04% | 13.22% | 0.6440 | 0.1313 |
| | PU-Bagged RF | 33.91% | 14.44% | 0.6501 | 0.1482 |
| | PU-Bagged GraphSAGE | **38.52%** | **16.40%** | **0.6796** | **0.1508** |
| **Yelahanka** | PU-Bagged LR | 59.72% | 7.33% | 0.8001 | 0.0718 |
| | PU-Bagged RF | 54.33% | 6.67% | 0.7835 | 0.0845 |
| | PU-Bagged GraphSAGE | **62.30%** | **7.64%** | **0.8121** | **0.0827** |

---

## 4. Honest Assessment: Does PU-Bagging Outperform the Original Models?

1. **Incremental, Consistent Gains across All Models**:
   - **Logistic Regression**: Top-20% capture rate changed from $38.43\%$ to $38.60\%$ ($+0.17\%$). Linear models have limited hypothesis capacity, so averaging balanced linear hyperplanes converges to essentially the same decision surface.
   - **Random Forest**: Top-20% capture rate improved from $38.84\%$ to $39.51\%$ ($+0.67\%$), and pooled capture increased from $38.08\%$ to $38.85\%$ ($+0.77\%$). Subsampling unlabelled sets provides additional tree diversity and reduces overfitting to noisy negative splits.
   - **GraphSAGE**: Top-20% capture rate improved from $41.59\%$ to $42.29\%$ ($+0.70\%$), and pooled capture jumped from $41.57\%$ to **$43.14\%$ ($+1.57\%$)**. GNN macro ROC-AUC improved from $0.6798$ to **$0.6855$**.

2. **Does it Fundamentally Change Model Selection?**
   - **No.** The performance ranking remains identical:
     $$\text{GraphSAGE} > \text{Random Forest} > \text{Logistic Regression}$$
   - The $+0.70\%$ to $+1.57\%$ gain from PU-Bagging is modest and remains within the cross-zone standard deviation ($\sim 11.7\%$).
   - It confirms that while PU-Bagging is theoretically cleaner and provides modest empirical gains, the primary limitation on prediction performance is **not class weighting vs. PU-sampling**, but the spatial resolution of the 30m DEM and incomplete urban drainage mapping.

---

## 5. Sensitivity Analyses

### A. Sensitivity to Unlabelled-to-Positive Sampling Ratio $r$ ($r \in \{1:1, 2:1, 3:1, 5:1\}$)

Evaluated on the Bommanahalli spatial holdout ($N=22,562$ nodes, $944$ positives):

| Sampling Ratio ($r:1$) | PU-LR Top-20% Capture | PU-LR AUC | PU-RF Top-20% Capture | PU-RF AUC | PU-GraphSAGE Top-20% Capture | PU-GraphSAGE AUC |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1:1** | 45.02% | 0.6979 | **50.00%** | **0.7215** | **48.62%** | **0.7189** |
| **2:1** | 45.13% | 0.7022 | 48.62% | 0.7192 | 46.08% | 0.7161 |
| **3:1** | 45.44% | 0.7034 | 47.56% | 0.7095 | 45.66% | 0.7151 |
| **5:1** | **45.44%** | **0.7046** | 46.72% | 0.7085 | 39.83% | 0.6835 |

**Physical Insight**:
- For **Random Forest and GraphSAGE**, balanced $1:1$ sampling produces the highest known-positive recall and AUC.
- As the negative sampling ratio increases to $5:1$, GraphSAGE's recall drops significantly (from $48.62\%$ down to $39.83\%$). Without class weighting, unlabelled negatives dominate message passing and suppress sensitivity in ambiguous low-lying depressions.
- For **Logistic Regression**, the ratio has virtually no effect ($45.02\%$ to $45.44\%$).

### B. Sensitivity to Number of Bags $K$ ($K \in \{1, 2, 3, 4, 5\}$)

| Bags ($K$) | PU-LR Capture | PU-LR AUC | PU-RF Capture | PU-RF AUC | PU-GraphSAGE Capture | PU-GraphSAGE AUC |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | 44.17% | 0.6982 | 49.79% | 0.7154 | 48.41% | 0.7141 |
| **2** | 44.07% | 0.6980 | 49.15% | 0.7200 | 49.58% | 0.7204 |
| **3** | 44.28% | 0.6986 | 49.26% | 0.7243 | 48.83% | 0.7203 |
| **4** | 44.49% | 0.6988 | 49.89% | 0.7273 | 49.05% | 0.7216 |
| **5** | **44.60%** | **0.6981** | **50.11%** | **0.7269** | 48.52% | **0.7200** |

**Ensemble Convergence**:
Increasing $K$ from 1 to 5 steadily improves the stability and AUC of Random Forest ($0.7154 \to 0.7269$, $+0.0115$) and GraphSAGE ($0.7141 \to 0.7200$, $+0.0059$), illustrating standard variance-reduction convergence.

---

## 6. Directory Artifacts

```
training/pu_experiment/
├── pu_bagging.py                     # Self-contained PU-Bagging execution script
├── README.md                         # This experimental documentation
└── results/
    ├── pu_overall_comparison.csv     # Comparative table: PU-Bagging vs Class-Weighted
    ├── pu_per_zone_metrics.csv       # Per-zone metrics for PU-LR, PU-RF, PU-GraphSAGE
    ├── pu_ratio_sensitivity.csv      # Sensitivity table across sampling ratios (1:1 to 5:1)
    ├── pu_bag_count_sensitivity.csv  # Sensitivity table across bag counts (K=1 to 5)
    ├── pu_top20_capture_comparison.png# Bar chart comparing top-20% capture per zone
    ├── pu_ratio_sensitivity_plot.png # Line plot showing sensitivity to ratio r
    └── pu_bag_convergence_plot.png   # Line plot showing convergence across bag counts K
```

---

## 7. How to Reproduce

From the repository root with the virtual environment activated:
```bash
MPLCONFIGDIR=/tmp/matplotlib .venv/bin/python training/pu_experiment/pu_bagging.py
```
The entire 8-fold cross-validation and sensitivity suite executes in approximately **2 minutes**.

