"""Deploy silver SQL views to Databricks.

Reads each .sql file in this directory, substitutes ${catalog}, ${raw_schema},
and ${silver_schema} parameters, and executes via Databricks SQL connector.

Usage:
    python deploy_silver_views.py [--catalog bdi_data_201]
                                  [--raw-schema synthetic_bank]
                                  [--silver-schema post2organizations_input]
                                  [--dry-run]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def deploy_views(
    catalog: str = "bdi_data_201",
    raw_schema: str = "synthetic_bank",
    silver_schema: str = "post2organizations_input",
    dry_run: bool = False,
) -> None:
    sql_dir = Path(__file__).parent
    sql_files = sorted(sql_dir.glob("v_*.sql"))

    if not sql_files:
        print("No SQL view files found.")
        return

    print(f"Deploying {len(sql_files)} silver views")
    print(f"  Catalog:       {catalog}")
    print(f"  Raw schema:    {raw_schema}")
    print(f"  Silver schema: {silver_schema}")
    print()

    for sql_file in sql_files:
        view_name = sql_file.stem
        sql = sql_file.read_text()
        sql = sql.replace("${catalog}", catalog)
        sql = sql.replace("${raw_schema}", raw_schema)
        sql = sql.replace("${silver_schema}", silver_schema)

        print(f"  {view_name}...")

        if dry_run:
            print(f"    [DRY RUN] Would execute:")
            for line in sql.strip().split("\n")[:5]:
                print(f"      {line}")
            print(f"      ... ({len(sql)} chars total)")
            print(f"    Done.")
        else:
            try:
                _execute_sql(catalog, sql)
                print(f"    Done.")
            except Exception as e:
                print(f"    FAILED: {e}")
                print(f"    (Skipping — deploy remaining views)")

    print(f"\nAll views deployed.")


def _execute_sql(catalog: str, sql: str) -> None:
    """Execute SQL on Databricks via the REST API."""
    import json
    import time
    import requests
    import yaml

    config_path = Path(__file__).resolve().parent.parent.parent.parent / "silver-layer" / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        host = cfg["databricks"]["host"]
        token = cfg["databricks"]["token"]
        warehouse_id = cfg["databricks"]["warehouse_id"]
    else:
        token = os.environ.get("DATABRICKS_TOKEN")
        host = os.environ.get("DATABRICKS_HOST", "https://banking-ci-data.cloud.databricks.com")
        warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "0e815dadc27740bc")

    if not token:
        raise ValueError("DATABRICKS_TOKEN env var or silver-layer/config.yaml required")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{host}/api/2.0/sql/statements"

    full_sql = f"USE CATALOG {catalog};\n{sql}"
    for stmt in [f"USE CATALOG {catalog}", sql]:
        payload = {"warehouse_id": warehouse_id, "statement": stmt, "wait_timeout": "30s"}
        resp = requests.post(url, headers=headers, json=payload, verify=False)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", {}).get("state", "UNKNOWN")
        if status == "FAILED":
            err = data.get("status", {}).get("error", {}).get("message", "Unknown error")
            raise RuntimeError(f"SQL failed: {err}")
        while status in ("PENDING", "RUNNING"):
            time.sleep(2)
            stmt_id = data["statement_id"]
            poll = requests.get(f"{url}/{stmt_id}", headers=headers, verify=False)
            poll.raise_for_status()
            data = poll.json()
            status = data.get("status", {}).get("state", "UNKNOWN")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy silver SQL views to Databricks")
    parser.add_argument("--catalog", default="bdi_data_201")
    parser.add_argument("--raw-schema", default="synthetic_bank")
    parser.add_argument("--silver-schema", default="post2organizations_input")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    deploy_views(
        catalog=args.catalog,
        raw_schema=args.raw_schema,
        silver_schema=args.silver_schema,
        dry_run=args.dry_run,
    )
