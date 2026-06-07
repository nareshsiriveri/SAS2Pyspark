"""Synthetic golden datasets consistent with examples/example.sas.

These mimic what a normal SAS run would write between steps, computed by hand so
the Spark-backed eval phases (schema / property / data-equivalence) have a ground
truth to compare against. Built lazily so importing this module never requires
pandas.
"""
from __future__ import annotations

import os


def build_frames():
    """Return a dict of {dataset_key: pandas.DataFrame} for the example pipeline."""
    import pandas as pd

    # raw.accounts — note region in mixed case and one balance <= 0 (filtered out).
    raw_accounts = pd.DataFrame(
        {
            "account_id": [1, 2, 3, 4],
            "region": ["us", "eu", "us", "eu"],
            "balance": [100.0, 200.0, -5.0, 50.0],
        }
    )
    raw_rates = pd.DataFrame({"region": ["US", "EU"], "rate": [0.10, 0.20]})

    # work.accounts: WHERE balance>0, region=UPCASE(region).
    work_accounts = pd.DataFrame(
        {
            "account_id": [1, 2, 4],
            "region": ["US", "EU", "EU"],
            "balance": [100.0, 200.0, 50.0],
        }
    )
    work_rates = raw_rates.copy()

    # work.priced: accounts LEFT JOIN rates ON region; interest = balance*rate.
    work_priced = pd.DataFrame(
        {
            "account_id": [1, 2, 4],
            "region": ["US", "EU", "EU"],
            "balance": [100.0, 200.0, 50.0],
            "rate": [0.10, 0.20, 0.20],
            "interest": [10.0, 40.0, 10.0],
        }
    )

    # work.cumulative: sorted by region, account_id; running_interest within region.
    work_cumulative = pd.DataFrame(
        {
            "account_id": [2, 4, 1],
            "region": ["EU", "EU", "US"],
            "balance": [200.0, 50.0, 100.0],
            "rate": [0.20, 0.20, 0.10],
            "interest": [40.0, 10.0, 10.0],
            "running_interest": [40.0, 50.0, 10.0],
        }
    )

    # work.region_summary: per-region aggregates.
    work_region_summary = pd.DataFrame(
        {
            "region": ["EU", "US"],
            "n_accounts": [2, 1],
            "total_balance": [250.0, 100.0],
            "total_interest": [50.0, 10.0],
        }
    )

    return {
        "raw.accounts": raw_accounts,
        "raw.rates": raw_rates,
        "work.accounts": work_accounts,
        "work.rates": work_rates,
        "work.priced": work_priced,
        "work.cumulative": work_cumulative,
        "work.region_summary": work_region_summary,
    }


def write_golden_dir(root: str, fmt: str = "csv") -> str:
    """Write all golden frames into ``root`` as ``<key>.<fmt>``; return ``root``."""
    from sas2spark.golden import write_golden_dataset

    os.makedirs(root, exist_ok=True)
    for key, df in build_frames().items():
        write_golden_dataset(df, os.path.join(root, f"{key}.{fmt}"))
    return root
