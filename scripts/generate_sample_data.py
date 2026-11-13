"""Generate a synthetic CAR-T batch dataset for trying out the dashboard.

Creates one column per parameter in config/parameters.csv, with values that
match the parameter's value type.

    python scripts/generate_sample_data.py
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
N_BATCHES = 2000
START, END = pd.Timestamp("2024-01-01"), pd.Timestamp("2026-09-01")
SITES = {"SITE-A": 1.0, "SITE-B": 0.97, "SITE-C": 1.03}

# Rough offset in days from manufacturing start, per process day.
DAY_OFFSET = {"Apheresis": -14, "Planning": -2, "D0": 0, "D1": 1, "D3": 3, "D6": 6, "D8": 8,
              "D10": 10, "Cryopreservation": 10, "Final Product": 11, "Post-Release": 30}


def _shift(rng, n):
    """For about a third of the parameters: a level shift of 1-2 SD at a random batch."""
    if rng.random() > 0.35:
        return np.zeros(n)
    return np.where(np.arange(n) >= rng.integers(n // 5, 4 * n // 5), rng.choice([-1, 1]) * rng.uniform(1, 2), 0)


def _numeric(rng, n, name, site_factor, t):
    if "%" in name:
        mean = rng.uniform(20, 95)
        sd = min(mean, 100 - mean) / 4 + 1
        values = rng.normal(mean, sd, n) + _shift(rng, n) * sd
        return np.clip(values * site_factor, 0, 100).round(1)
    scale = 10 ** rng.uniform(-1, 7)
    # Slow drift over time, sometimes a shift, plus a small site effect.
    values = scale * rng.lognormal(0, 0.15, n) * (1 + 0.15 * _shift(rng, n))
    values *= site_factor * (1 + rng.normal(0, 0.1) * t)
    return values.round(3) if scale < 100 else values.round(0)


def _categorical(rng, n, name, day):
    if re.search(r"lot|batch|\bid\b|#|number|din", name, re.I):
        # Lots in use change over time: each lot covers a stretch of consecutive batches.
        lot_len = int(rng.integers(20, 120))
        prefix = "".join(w[0] for w in re.findall(r"[A-Za-z]+", name))[:4].upper()
        return np.array([f"{prefix}-{i // lot_len + 1:04d}" for i in range(n)], dtype=object)
    if "(y/n)" in name.lower() or name.endswith("?"):
        p_yes = 0.95 if "completed" in name.lower() else rng.uniform(0.02, 0.2)
        return np.where(rng.random(n) < p_yes, "Y", "N")
    k = int(rng.integers(2, 6))
    return rng.choice([f"Category {c}" for c in "ABCDE"[:k]], n, p=rng.dirichlet(np.ones(k) * 2))


def _datetime(rng, n, name, mfg, day):
    offset = pd.to_timedelta(DAY_OFFSET.get(day, 0) + rng.normal(0, 0.1, n), unit="D")
    stamps = (mfg + offset + pd.to_timedelta(rng.uniform(8, 17, n), unit="h")).dt.round("min")
    if "hh:mm" in name.lower():
        return stamps.dt.strftime("%H:%M").to_numpy()
    return stamps.dt.strftime("%Y-%m-%d %H:%M").to_numpy()


def _duration(rng, n):
    """Durations in minutes, between about 10 minutes and 3 days."""
    mean = rng.uniform(10, 4320)
    return np.clip(rng.normal(mean, mean * 0.1, n), 0, None).round(0)


def generate(params: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = N_BATCHES
    days = np.sort(rng.integers(0, (END - START).days, n))
    mfg = pd.Series(START + pd.to_timedelta(days, unit="D"))
    t = days / days.max()
    sites = rng.choice(list(SITES), n, p=[0.45, 0.35, 0.2])
    site_factor = np.array([SITES[s] for s in sites])

    columns = {}
    for name, vtype, day in params[["Parameter", "Value Type", "Process Day"]].itertuples(index=False):
        vtype = str(vtype).strip()
        if name == "Patient Lot/Batch #":
            values = np.array([f"CT{d.year % 100:02d}-{i + 1:05d}" for i, d in enumerate(mfg)])
        elif name == "Date of Manufacture Start":
            values = mfg.dt.strftime("%Y-%m-%d").to_numpy()
        elif name == "Manufacturing Site":
            values = sites
        elif name in ("Remanufacture", "Re-MFG (Y/N)"):
            values = columns.get("Remanufacture", np.where(rng.random(n) < 0.08, "Y", "N"))
        elif vtype.startswith("["):
            levels = [c.strip() for c in vtype[1:-1].split(",")]
            values = rng.choice(levels, n, p=np.linspace(len(levels), 1, len(levels)) / sum(range(1, len(levels) + 1)))
        elif vtype == "categorical":
            values = _categorical(rng, n, name, day)
        elif vtype == "datetime":
            values = _datetime(rng, n, name, mfg, day)
        elif vtype == "duration":
            values = _duration(rng, n)
        elif vtype == "ratio":
            values = rng.normal(rng.uniform(0.2, 2), 0.05, n).round(3)
        elif vtype == "numeric":
            values = _numeric(rng, n, name, site_factor, t)
        else:  # e.g. TODO
            values = np.where(rng.random(n) < 0.99, "Negative", "Positive")
        columns[name] = values

    df = pd.DataFrame(columns)
    # A few missing values, as in real data. The selection columns stay complete.
    keep_complete = ["Patient Lot/Batch #", "Date of Manufacture Start", "Manufacturing Site", "Remanufacture"]
    others = [c for c in df.columns if c not in keep_complete]
    df[others] = df[others].mask(rng.random((n, len(others))) < 0.02)
    return df


if __name__ == "__main__":
    params = pd.read_csv(ROOT / "config" / "parameters.csv", sep=";", encoding="utf-8-sig")
    out = ROOT / "data" / "sample_batches.csv.gz"
    generate(params).to_csv(out, index=False)
    print(f"Wrote {out}")
