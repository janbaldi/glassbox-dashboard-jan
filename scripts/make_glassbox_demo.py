"""Build a glassbox OOS dataset from the sample batches, for trying *Open glassbox run*.

Takes the synthetic sample data, keeps a set of numeric parameters, and plants an
out-of-spec label driven by three of them. Writes ``dataset.csv`` and a small,
fast glassbox config (few tuning trials, 10 leave-one-out dossiers) to ``data/glassbox_demo/``. Then run glassbox on it (in its
own environment, Python 3.12):

    python main.py --config <demo>/config_demo.yaml --data-path <demo>/dataset.csv \\
        --target-col car_oos_y_n_is_y --task classification --models all \\
        --output-dir <demo>/run --id-col "Patient Lot/Batch #" --impute-strategy median

and open ``data/glassbox_demo/run`` in the dashboard. The script prints the exact
command.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample_batches.csv.gz"
PARAMETERS = ROOT / "catalog.xlsx"
OUT = ROOT / "data" / "glassbox_demo"
BATCH_ID = "Patient Lot/Batch #"
TARGET = "car_oos_y_n_is_y"
N_FEATURES = 30

# What makes a batch fail in this demo, as weights on z-scores.
DRIVERS = {
    "Vector hold time (min)": 1.4,
    "Prodigy Total Viable Cell Step Yield (%)": -1.2,
    "Thaw Duration (min)": 0.9,
}
INTERCEPT = -3.6

CONFIG = """\
report:
  title: Demo OOS investigation
  description: >-
    Synthetic sample batches with an out-of-spec label planted on vector hold
    time, Prodigy step yield and thaw duration. For trying the dashboard's
    Open glassbox run.

pipeline:
  cv_strategy: stratified_kfold
  n_splits: 3
  random_state: 42
  tuning_n_trials: 4
  calibration: sigmoid

investigation:
  batches: all_oos
  max_detail: 10
  preselect: 1

ebm:
  learning_rate: [0.01, 0.05]
  max_bins: [256]
  max_interaction_bins: [16]
  interactions: [0, 3]
  min_samples_leaf: [2]
  max_leaves: [2, 3]

xgboost:
  learning_rate: [0.05, 0.1]
  max_depth: [2]
  n_estimators: [200, 400]
  subsample: [0.7, 1]
  colsample_bytree: [0.7, 1]

pygam:
  lam: [0.1, 1.0, 10.0]
  n_splines: [10]

decision_tree:
  max_depth: [3, 5]
  min_samples_leaf: [5, 20]
  ccp_alpha: [0.0, 0.001]
"""


def main(seed: int = 11) -> None:
    rng = np.random.default_rng(seed)
    df = pd.read_csv(SAMPLE, low_memory=False)
    params = pd.read_excel(PARAMETERS)
    numeric = [
        p for p in params.loc[params["Value Type"] == "numeric", "Parameter"]
        if p in df.columns and df[p].notna().mean() > 0.9 and p not in DRIVERS
    ]
    others = list(rng.choice(numeric, N_FEATURES - len(DRIVERS), replace=False))
    features = list(DRIVERS) + others

    z = {f: (df[f] - df[f].mean()) / df[f].std() for f in DRIVERS}
    logit = INTERCEPT + sum(w * z[f].fillna(0) for f, w in DRIVERS.items())
    y = (rng.random(len(df)) < 1 / (1 + np.exp(-logit))).astype(int)

    OUT.mkdir(parents=True, exist_ok=True)
    data = df[[BATCH_ID] + features].assign(**{TARGET: y})
    data.to_csv(OUT / "dataset.csv", index=False)
    (OUT / "config_demo.yaml").write_text(CONFIG)
    print(f"{len(data)} batches, {y.sum()} OOS ({y.mean():.1%}), {len(features)} features -> {OUT}")
    print(
        "\nRun glassbox from its folder:\n"
        f'  python main.py --config {OUT / "config_demo.yaml"} --data-path {OUT / "dataset.csv"} '
        f"--target-col {TARGET} --task classification --models all "
        f'--output-dir {OUT / "run"} --id-col "{BATCH_ID}" --impute-strategy median'
    )


if __name__ == "__main__":
    main()
