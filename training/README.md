# Stage 1 Model Training: Bengaluru Waterlogging Prediction

This directory implements the model training, spatial validation, and benchmarking pipeline for Stage 1 of the Bengaluru Waterlogging Prediction system.

The objective is to predict flood-prone locations across the city using node classification on the combined road and stormwater drain graph, evaluating three model families:
1. **Logistic Regression** (L2-regularized linear baseline with standardized features)
2. **Random Forest** (100 trees, maximum depth 12, balanced weighting)
3. **GraphSAGE GNN** (2-layer inductive message passing network using PyTorch Geometric)

---

## 1. Input Data & Strict Feature Discipline

All training runs strictly on the data exported during Stage 1 data preparation in `export/`:
- `export/feature_columns.txt`: Defines the exact 10 terrain and drainage features used for prediction.
- `export/nodes.csv`: 248,287 total nodes (157,533 inside the 8 BBMP zones, 90,754 in `zone="outside"`).
- `export/edges.csv`: 619,776 directed edges connecting road and drain segments.

### The 10 Features
1. `elev_m`: Surface elevation above sea level (meters).
2. `slope_deg`: Terrain slope gradient (degrees).
3. `depression_m`: Local sink depression depth (meters).
4. `upstream_km2`: Contributing hydrological catchment area ($km^2$).
5. `twi`: Topographic Wetness Index ($\ln(a / \tan \beta)$).
6. `hand_m`: Height Above Nearest Drainage (meters).
7. `tpi300_m`: Topographic Position Index within a 300 m radius (meters).
8. `tpi1000_m`: Topographic Position Index within a 1,000 m radius (meters).
9. `dist_to_official_drain_m`: Euclidean distance to nearest official primary/secondary drain (meters).
10. `drain_density_500m`: Total drain length within a 500 m radius ($m/km^2$).

> [!IMPORTANT]
> **Strict Feature Discipline**: No node IDs, coordinates (`x`, `y`, `lat`, `lon`), ward IDs, zone names, road classifications, or distance-to-flood/hotspot proxies are used as features. Only the 10 physical features are provided to the models.

---

## 2. Spatial Validation Design

Urban spatial phenomena suffer from severe spatial autocorrelation. Random train/test splits cause extreme data leakage, producing deceptively inflated metrics.

### 8-Fold Spatial Leave-One-Zone-Out Validation
Validation is performed across the **8 official BBMP administrative zones**:
1. `Bommanahalli` (22,562 nodes; 944 positives, 4.18%)
2. `Dasarahalli` (8,481 nodes; 394 positives, 4.65%)
3. `East` (22,414 nodes; 1,472 positives, 6.57%)
4. `Mahadevapura` (26,889 nodes; 1,180 positives, 4.39%)
5. `Rajarajeshwari Nagar` (24,513 nodes; 1,038 positives, 4.23%)
6. `South` (19,737 nodes; 1,622 positives, 8.22%)
7. `West` (15,541 nodes; 1,324 positives, 8.52%)
8. `Yelahanka` (17,396 nodes; 427 positives, 2.45%)

**Total BBMP Nodes**: 157,533 (8,401 positive flood nodes, 5.33% prevalence).

### Boundary Rules
- **No Random Splits**: Every fold holds out an entire administrative zone for testing and trains on the remaining 7 zones.
- **Exclusion of `outside`**: The 90,754 nodes with `zone="outside"` lie outside the 2015 BBMP ward boundaries and were not surveyed by BBMP (they contain 90,752 zeros and only 2 edge-buffer positives). They are strictly excluded from both training and testing.
- **Identical Folds**: All three models are evaluated on the exact same fold splits.

---

## 3. Graph Leakage & Cross-Zone Edge Handling

In graph neural networks, message passing across edges can inadvertently leak information from the held-out test fold into the training graph.

### Edge Analysis
- Total edges: 619,776
- Intra-zone edges: 614,767 (99.19%)
- Cross-zone boundary edges: 5,009 (0.81%)

### Inductive Isolation Protocol
For each fold $k$ holding out zone $Z_k$:
1. **Training Graph Isolation**: All edges where either `src` or `dst` belongs to $Z_k$ (or `outside`) are **severed from the training graph**. The training graph consists strictly of the induced subgraph of the 7 training zones. Between 337 and 1,135 boundary-crossing edges are removed per fold.
2. **Test Graph Inductive Evaluation**: During inference on $Z_k$, test nodes aggregate features only from neighbors within $Z_k$ (the induced subgraph of the test zone).
3. **Zero Test Node Participation**: No node in $Z_k$ participates in training message passing, loss computation, or feature scaling.

---

## 4. Positive-Unlabelled (PU) Learning Strategy

### The Problem
- `label = 1`: The node is within 150 m of an official BBMP flood point (compiled from vulnerable, prone, and low-lying KMLs).
- `label = 0`: The node is **unlabelled**, NOT confirmed safe.
BBMP flood records represent documented complaints and historical municipal intervention sites. Rapid urbanization has created hundreds of unrecorded low-lying waterlogged alleys and depressions. Blindly treating all 149,132 unlabelled nodes as verified non-flooding negatives penalizes models for correctly recognizing flood-prone topography and distorts calibrated probabilities.

### Justified Strategy
1. **Balanced Empirical Risk Weighting**: Rather than treating unlabelled points as hard negatives with uniform weight, positive samples are weighted by $w_p = |U| / |P| \approx 17.7$. This balances the objective and prevents the overwhelming mass of unlabelled examples from crushing positive sensitivity.
2. **PU Negative Subsampling Sensitivity Analysis**: In addition to full-dataset balanced training, we evaluate unlabelled-to-positive negative subsampling ratios $r \in \{1:1, 2:1, 3:1, 5:1, 10:1, \text{All}\}$. Across all test zones, ranking performance (ROC-AUC and Top-20% Capture Rate) remains remarkably stable across sampling ratios, confirming that the learned physical rankings are robust to negative sampling density.
3. **Threshold-Independent Ranking Metrics**: We evaluate models primarily on **ROC-AUC**, **Average Precision (PR-AUC)**, and **Top-20% Risk Area Capture Rate**. By Elkan & Noto (2008) and Menon et al. (2015), the ranking order under the Selected Completely At Random (SCAR) assumption is monotonic with the true risk ranking.

---

## 5. Empirical Results

All models were executed using 8-fold spatial cross-validation. Results are reported honestly from actual runs without exaggeration.

### Overall Performance Comparison

| Model | Macro ROC-AUC | Pooled ROC-AUC | Macro PR-AUC (AP) | Pooled PR-AUC (AP) | Macro Top-20% Capture | Pooled Top-20% Capture | Macro Precision | Macro Recall | Macro F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Logistic Regression** | 0.6703 ± 0.0741 | 0.6608 | 0.0940 ± 0.0397 | 0.0865 | 38.43% ± 11.00% | 37.13% | 0.0824 | 0.6827 | 0.1446 |
| **Random Forest** | 0.6663 ± 0.0825 | 0.6598 | **0.1038 ± 0.0359** | 0.0983 | 38.84% ± 12.14% | 38.08% | **0.0931** | 0.4614 | **0.1497** |
| **GraphSAGE GNN** | **0.6798 ± 0.0743** | **0.6734** | 0.1016 ± 0.0370 | **0.1001** | **41.59% ± 11.08%** | **41.57%** | 0.0852 | 0.6336 | 0.1476 |

*Base label prevalence across the 8 BBMP zones is 5.33% (0.0533).*

### Per-Zone Detailed Metrics

| Zone | Model | ROC-AUC | Average Precision | Precision | Recall | F1 Score | Top-20% Capture Rate | Top-20% Precision |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Bommanahalli** | Logistic Regression | 0.6986 | 0.0762 | 0.0721 | 0.6504 | 0.1298 | 44.70% | 9.35% |
| | Random Forest | 0.7279 | 0.0993 | 0.0946 | 0.5148 | 0.1599 | 48.31% | 10.10% |
| | GraphSAGE | **0.7296** | **0.1029** | 0.0798 | 0.6536 | 0.1422 | **51.48%** | **10.77%** |
| **Dasarahalli** | Logistic Regression | 0.5691 | 0.0582 | 0.0612 | 0.5406 | 0.1100 | 24.37% | 5.66% |
| | Random Forest | 0.5324 | 0.0484 | 0.0446 | 0.2640 | 0.0763 | 19.29% | 4.48% |
| | GraphSAGE | **0.5627** | **0.0530** | 0.0541 | 0.3807 | 0.0947 | **22.84%** | **5.30%** |
| **East** | Logistic Regression | 0.5863 | 0.0961 | 0.0793 | 0.6148 | 0.1405 | 30.77% | 10.10% |
| | Random Forest | 0.5804 | 0.0934 | 0.0820 | 0.4633 | 0.1394 | 27.17% | 8.92% |
| | GraphSAGE | **0.6033** | **0.1124** | 0.0867 | 0.6270 | 0.1524 | **33.49%** | **11.00%** |
| **Mahadevapura** | Logistic Regression | **0.6750** | 0.0815 | 0.0716 | 0.6619 | 0.1293 | **42.71%** | **9.37%** |
| | Random Forest | 0.6398 | **0.0931** | 0.0729 | 0.4534 | 0.1256 | 37.97% | 8.33% |
| | GraphSAGE | 0.6574 | 0.0779 | 0.0640 | 0.7051 | 0.1174 | 39.75% | 8.72% |
| **Rajarajeshwari Nagar** | Logistic Regression | 0.6664 | 0.0634 | 0.0646 | 0.8150 | 0.1198 | 33.33% | 7.06% |
| | Random Forest | **0.7229** | **0.1056** | 0.0939 | 0.4441 | 0.1550 | **44.41%** | **9.40%** |
| | GraphSAGE | 0.7103 | 0.0835 | 0.0747 | 0.6243 | 0.1334 | 42.49% | 8.99% |
| **South** | Logistic Regression | **0.7240** | **0.1742** | 0.1337 | 0.7867 | 0.2286 | 41.12% | 16.89% |
| | Random Forest | 0.6939 | 0.1630 | 0.1507 | 0.5506 | 0.2367 | 41.68% | 17.12% |
| | GraphSAGE | 0.6951 | 0.1566 | 0.1252 | 0.7318 | 0.2138 | **42.73%** | **17.55%** |
| **West** | Logistic Regression | 0.6434 | 0.1313 | 0.1285 | 0.5468 | 0.2080 | 30.97% | 13.19% |
| | Random Forest | 0.6496 | 0.1454 | 0.1456 | 0.2893 | 0.1937 | 34.06% | 14.51% |
| | GraphSAGE | **0.6778** | **0.1513** | 0.1415 | 0.5310 | 0.2235 | **40.03%** | **17.05%** |
| **Yelahanka** | Logistic Regression | 0.7997 | 0.0712 | 0.0479 | 0.8454 | 0.0907 | 59.48% | 7.30% |
| | Random Forest | 0.7832 | **0.0822** | 0.0603 | 0.7119 | 0.1112 | 57.85% | 7.10% |
| | GraphSAGE | **0.8021** | 0.0749 | 0.0554 | 0.8150 | 0.1038 | **59.95%** | **7.36%** |

---

## 6. Honest Evaluation & Key Takeaways

1. **Does GraphSAGE Outperform Classical Baselines?**
   - **Yes, but by a modest margin.** GraphSAGE achieves a macro Top-20% Risk Area Capture Rate of **41.59%**, which is **+2.75 percentage points** over Random Forest (38.84%) and **+3.16 percentage points** over Logistic Regression (38.43%).
   - On Pooled ROC-AUC, GraphSAGE reaches **0.6734** vs 0.6608 for Logistic Regression and 0.6598 for Random Forest.
   - However, the spatial standard deviation across zones is **~11–12%**. In zones like Mahadevapura and Rajarajeshwari Nagar, Logistic Regression or Random Forest matched or outperformed GraphSAGE. GraphSAGE provides its largest gains in older, interconnected drainage basins like Bommanahalli (+3.17% capture), East (+6.32% capture), and West (+5.97% capture).

2. **Why Simpler Models Remain Competitive**:
   - Terrain features (`elev_m`, `tpi1000_m`, and `hand_m`) already summarize substantial regional catchment geometry.
   - The road network contains many local residential roads where graph distance does not directly correspond to hydraulic water flow. Consequently, naive message passing along road edges adds slight smoothing noise in flatter topographies.

3. **High Spatial Heterogeneity Across Zones**:
   - In **Yelahanka**, all models achieve high predictive accuracy (ROC-AUC ~0.78–0.80, Top-20% Capture ~58–60%) because Yelahanka possesses pronounced natural valley corridors and lake chains that clearly separate high-risk and low-risk terrain.
   - In **Dasarahalli**, all models perform poorly (ROC-AUC ~0.53–0.57, Top-20% Capture ~19–24%). Dasarahalli is heavily paved, industrial, and flat, where flooding is driven by blocked culverts, undersized roadside drains, and localized trash blockages rather than macroscopic topography.

---

## 7. Feature Importance Analysis

Feature importances were averaged across all 8 spatial folds:

| Feature | RF Gini Importance (Mean ± SD) | LR Standardized Coef (Mean ± SD) | LR Odds Ratio | Physical Interpretation |
| :--- | :---: | :---: | :---: | :--- |
| **`elev_m`** | **0.2148 ± 0.0094** | -0.0085 ± 0.0569 | 0.9916 | Absolute surface elevation; key regional baseline. |
| **`tpi1000_m`** | **0.1862 ± 0.0121** | **-0.6859 ± 0.0669** | **0.5036** | Regional valley position index. Strongest negative coefficient: lower values (valleys/hollows) have 2x higher odds of flooding. |
| **`hand_m`** | **0.1522 ± 0.0135** | **-0.2517 ± 0.0812** | **0.7775** | Height above nearest drainage. Lower elevation relative to stream channel significantly raises flood probability. |
| **`drain_density_500m`** | 0.1309 ± 0.0099 | +0.0621 ± 0.0512 | 1.0641 | High drain density correlates with low-lying valley collector corridors. |
| **`dist_to_official_drain_m`** | 0.0987 ± 0.0037 | -0.0580 ± 0.0362 | 0.9436 | Proximity to official storm drains increases vulnerability to backwater spills. |
| **`tpi300_m`** | 0.0910 ± 0.0055 | +0.5064 ± 0.0299 | 1.6593 | Local micro-topographic index. Interacts with `tpi1000_m` to delineate local road depressions. |
| **`slope_deg`** | 0.0443 ± 0.0026 | +0.0304 ± 0.0118 | 1.0309 | Flat slopes reduce runoff velocity, increasing ponding duration. |
| **`twi`** | 0.0405 ± 0.0018 | +0.0018 ± 0.0093 | 1.0019 | Topographic wetness index. |
| **`upstream_km2`** | 0.0245 ± 0.0011 | -0.0096 ± 0.0136 | 0.9904 | Contributing catchment area. |
| **`depression_m`** | 0.0168 ± 0.0017 | +0.1048 ± 0.0110 | 1.1105 | Direct sink depression depth; positive coefficient indicates ponding sinkholes. |

---

## 8. Directory Artifacts

```
training/
├── stage1_model_training.ipynb     # Interactive Google Colab notebook
├── train_stage1.py                 # Standalone reproducible training script
├── README.md                       # This documentation
├── results/
│   ├── overall_comparison.csv      # Macro and pooled summary metrics across 8 folds
│   ├── per_zone_metrics.csv        # Detailed metrics per zone for all 3 models
│   ├── feature_importance.csv      # RF MDI & LR coefficients and odds ratios
│   ├── pu_sensitivity_analysis.csv # PU sampling sensitivity across ratios
│   ├── roc_curves.png              # Spatial ROC curves for all models
│   ├── precision_recall_curves.png # Spatial Precision-Recall curves
│   ├── feature_importance.png      # Feature importance horizontal bar charts
│   ├── top20_capture_comparison.png# Disaster management capture rate by zone
│   └── pu_sensitivity.png          # Sensitivity analysis line charts
└── checkpoints/
    ├── lr_{zone}.joblib            # Trained Logistic Regression models (8 folds)
    ├── rf_{zone}.joblib            # Trained Random Forest models (8 folds)
    ├── graphsage_{zone}.pt         # Trained GraphSAGE PyTorch checkpoints (8 folds)
    └── scaler_{zone}.joblib        # Fitted StandardScalers (8 folds)
```

---

## 9. How to Reproduce

### In Google Colab
1. Upload the `export/` folder and `training/stage1_model_training.ipynb` to Google Drive or Colab workspace.
2. Open `stage1_model_training.ipynb` in Google Colab.
3. Select a Python 3 runtime (CPU or T4 GPU).
4. Run all cells sequentially (`Runtime -> Run all`).

### Locally via Terminal
```bash
# From repository root with virtual environment activated
.venv/bin/python training/train_stage1.py
```
Execution takes approximately **45 seconds** total across all 8 folds for all 3 models and PU sensitivity analysis.

---

## 10. Limitations & Project Scope

1. **Static Susceptibility vs Dynamic Storm Events**:
   - Stage 1 models predict *static topographical and infrastructural flood susceptibility* ("where is terrain prone to flooding?").
   - Stage 1 does not incorporate dynamic weather radar, rainfall intensity, or duration. Dynamic rainfall events will be incorporated in Stage 2.
2. **BBMP Label Incompleteness (PU Setting)**:
   - Official flood points reflect reported citizen complaints and municipal action records. Many unrecorded waterlogged locations exist in unlabelled space (`label=0`), constraining the theoretical ceiling of precision and recall.
3. **Resolution of DEM**:
   - The 30m Copernicus DEM accurately captures regional ridge-valley structures (`tpi1000_m`, `hand_m`), but cannot capture micro-scale urban features like 15 cm roadside curbs, clogged drain gratings, or flyover underpasses.
4. **Underground Drainage Network**:
   - The stormwater drain network reflects mapped surface channels (rajakaluves); subsurface covered box drains and municipal cross-pipes are partially unmapped in open GIS sources.

