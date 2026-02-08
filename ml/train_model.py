# train_model.py
"""
Train a stacked anomaly detector on your CSV datasets.

Uses:
- system-*.csv (load, cpu-user, cpu-system, disk, etc.)
- CloudAnomalyDataset.csv (cloud anomalies with labels)
- systemresources-deeplearning-1000.csv (cpu/ram/disk/network)

Outputs:
- trained_detector.pkl  (model + scaler + feature list)
"""

import pandas as pd
import numpy as np
import glob
import os
from pathlib import Path
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import StackingClassifier, IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
import warnings

warnings.filterwarnings("ignore")


def pick_col(df: pd.DataFrame, candidates):
    """Return first matching column name from candidates (case-insensitive)."""
    # Exact match first
    for c in candidates:
        if c in df.columns:
            return c
    # Case-insensitive match
    lower_map = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


print("🔥 Training stacked anomaly detector on your CSV datasets")

# --------------------------------------------------------------------
# Step 1: Find CSV files (current dir + parent + /home/kartik)
# --------------------------------------------------------------------
search_paths = [".", "..", "../..", "/home/kartik"]
all_csvs = []

for base in search_paths:
    if os.path.exists(base):
        all_csvs.extend(
            glob.glob(os.path.join(base, "**", "*.csv"), recursive=True)
        )

print(f"\n🔍 Found {len(all_csvs)} CSV files")
if not all_csvs:
    raise ValueError("No CSV files found. Check paths.")

system_files = [f for f in all_csvs if "system-" in os.path.basename(f)]
cloud_file = next(
    (f for f in all_csvs if "CloudAnomalyDataset" in os.path.basename(f)),
    None,
)
deep_file = next(
    (
        f
        for f in all_csvs
        if "systemresources-deeplearning-1000" in os.path.basename(f)
    ),
    None,
)

print(f"\n📊 System files: {len(system_files)}")
print(f"📊 Cloud file: {cloud_file}")
print(f"📊 Deeplearning file: {deep_file}")

# --------------------------------------------------------------------
# Step 2: Load system-*.csv files
# --------------------------------------------------------------------
system_df_list = []
print("\n📥 Loading system-*.csv files (CPU/load metrics)...")

for file in system_files:
    try:
        df = pd.read_csv(file)
        # Choose best metric column as 'metric_value'
        metric_col = pick_col(
            df,
            [
                "cpu-user",
                "cpu_user",
                "cpu-system",
                "cpu_system",
                "cpu",
                "CPU",
                "load-1m",
            ],
        )
        if metric_col is None:
            print(f"  ⚠️ Skip {file}: no CPU/load column")
            continue

        tmp = pd.DataFrame()
        tmp["metric_value"] = df[metric_col]
        tmp["source"] = "system"
        system_df_list.append(tmp)
        print(f"  ✅ {file}: rows={len(tmp)}, metric={metric_col}")
    except Exception as e:
        print(f"  ❌ {file}: {e}")

if system_df_list:
    system_df = pd.concat(system_df_list, ignore_index=True)
    print(f"✅ Combined system data: {system_df.shape}")
else:
    system_df = pd.DataFrame()
    print("⚠️ No system data loaded")

# --------------------------------------------------------------------
# Step 3: Load CloudAnomalyDataset.csv
# --------------------------------------------------------------------
cloud_df = pd.DataFrame()
if cloud_file:
    print("\n📥 Loading CloudAnomalyDataset...")
    try:
        raw = pd.read_csv(cloud_file)
        print("  Cloud columns:", raw.columns.tolist())

        cpu_col = pick_col(
            raw, ["cpuusage", "cpu_usage", "CPUUsage", "cpu", "CPU"]
        )
        mem_col = pick_col(
            raw,
            ["memoryusage", "memory_usage", "MemoryUsage", "mem", "ram"],
        )

        if cpu_col is None and mem_col is None:
            print("  ⚠️ No CPU/memory column in cloud dataset, skipping")
        else:
            dfc = pd.DataFrame()
            if cpu_col is not None and mem_col is not None:
                dfc["metric_value"] = raw[cpu_col].fillna(raw[mem_col])
            elif cpu_col is not None:
                dfc["metric_value"] = raw[cpu_col]
            else:
                dfc["metric_value"] = raw[mem_col]

            label_col = pick_col(
                raw,
                [
                    "Anomaly status",
                    "anomaly_status",
                    "Anomaly",
                    "label",
                    "Label",
                ],
            )
            if label_col is not None:
                dfc["is_anomaly"] = (raw[label_col] == 1).astype(int)
                print(f"  ✅ Using label column: {label_col}")
            else:
                print("  ⚠️ No label column in cloud dataset")

            dfc["source"] = "cloud"
            cloud_df = dfc
            print(f"  ✅ Cloud data shape: {cloud_df.shape}")
    except Exception as e:
        print(f"  ❌ Failed to load cloud dataset: {e}")
else:
    print("\n⚠️ No CloudAnomalyDataset.csv found")

# --------------------------------------------------------------------
# Step 4: Load systemresources-deeplearning-1000.csv
# --------------------------------------------------------------------
deep_df = pd.DataFrame()
if deep_file:
    print("\n📥 Loading systemresources-deeplearning-1000.csv...")
    try:
        raw = pd.read_csv(deep_file)
        print("  Deep columns:", raw.columns.tolist())
        cpu_col = pick_col(raw, ["cpu", "CPU"])
        if cpu_col is None:
            print("  ⚠️ No CPU column in deeplearning dataset, skipping")
        else:
            dfd = pd.DataFrame()
            dfd["metric_value"] = raw[cpu_col]
            dfd["source"] = "deeplearning"
            deep_df = dfd
            print(f"  ✅ Deeplearning data shape: {deep_df.shape}")
    except Exception as e:
        print(f"  ❌ Failed to load deeplearning dataset: {e}")
else:
    print("\n⚠️ No systemresources-deeplearning-1000.csv found")

# --------------------------------------------------------------------
# Step 5: Combine all datasets
# --------------------------------------------------------------------
df_parts = [d for d in [system_df, cloud_df, deep_df] if not d.empty]
if not df_parts:
    raise ValueError("No usable data from any CSVs. Check file locations and formats.")

df = pd.concat(df_parts, ignore_index=True)
print(f"\n🎉 Combined dataset shape: {df.shape}")

# --------------------------------------------------------------------
# Step 6: Feature engineering
# --------------------------------------------------------------------
print("\n🔧 Feature engineering...")

df = df.dropna(subset=["metric_value"])
df["metric_value_log"] = np.log1p(df["metric_value"])
df["lag1"] = df["metric_value"].shift(1).fillna(method="bfill")
df["lag3"] = df["metric_value"].shift(3).fillna(method="bfill")
df["rolling_mean_5"] = (
    df["metric_value"].rolling(window=5).mean().fillna(method="bfill")
)
df["rolling_std_5"] = (
    df["metric_value"].rolling(window=5).std().fillna(1.0)
)

# Fake time features (no real timestamps here)
n = len(df)
df["hour"] = (np.arange(n) % 24).astype(float)
df["day_of_week"] = (np.arange(n) % 7).astype(float)

df = df.replace([np.inf, -np.inf], np.nan).fillna(0)

# Labels:
if "is_anomaly" in df.columns:
    print("✅ Using existing is_anomaly labels where present")
    # Some rows (system/deep) may have NaN labels → generate for them
    if df["is_anomaly"].isna().any():
        mask = df["is_anomaly"].isna()
        z = (df.loc[mask, "metric_value"] - df.loc[mask, "rolling_mean_5"]) / df.loc[
            mask, "rolling_std_5"
        ]
        df.loc[mask, "is_anomaly"] = (np.abs(z) > 3).astype(int)
else:
    print("🔮 No labels; generating from 3-sigma rule")
    z = (df["metric_value"] - df["rolling_mean_5"]) / df["rolling_std_5"]
    df["is_anomaly"] = (np.abs(z) > 3).astype(int)

df["is_anomaly"] = df["is_anomaly"].astype(int)

print("Label distribution:")
print(df["is_anomaly"].value_counts(normalize=True))

feature_cols = [
    "metric_value",
    "metric_value_log",
    "lag1",
    "lag3",
    "rolling_mean_5",
    "rolling_std_5",
    "hour",
    "day_of_week",
]

X = df[feature_cols].values
y = df["is_anomaly"].values

print(f"✅ Feature matrix X shape: {X.shape}, y shape: {y.shape}")

# --------------------------------------------------------------------
# Step 7: Train / test split
# --------------------------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

print(f"\n📊 Train set: {X_train_scaled.shape}, Test set: {X_test_scaled.shape}")

# --------------------------------------------------------------------
# Step 8: Stacking model
# --------------------------------------------------------------------
print("\n🤖 Training stacking classifier...")

base_models = [
    ("isolation_forest", IsolationForest(contamination=0.1, random_state=42)),
    ("oneclass_svm", OneClassSVM(nu=0.1, kernel="rbf")),
]

meta_model = LogisticRegression(random_state=42, class_weight="balanced")

stacking_clf = StackingClassifier(
    estimators=base_models,
    final_estimator=meta_model,
    cv=3,
    n_jobs=-1,
)

stacking_clf.fit(X_train_scaled, y_train)

# --------------------------------------------------------------------
# Step 9: Evaluation
# --------------------------------------------------------------------
y_pred = stacking_clf.predict(X_test_scaled)
try:
    y_proba = stacking_clf.predict_proba(X_test_scaled)[:, 1]
    auc = roc_auc_score(y_test, y_proba)
except Exception:
    y_proba = None
    auc = None

print("\n📈 Classification report:")
print(classification_report(y_test, y_pred))
if auc is not None:
    print(f"ROC-AUC: {auc:.3f}")

out_path = "trained_detector.pkl"
joblib.dump(
    {
        "model": stacking_clf,
        "scaler": scaler,
        "features": feature_cols,
    },
    out_path,
)

print(f"\n🎉 Saved trained model to {out_path}")
print("➡ Copy this file into your ml/ folder and point anomaly_detection.py to it.")