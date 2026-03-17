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
        else:
            _execute_sql(catalog, sql)

        print(f"    Done.")

    print(f"\nAll views deployed.")


def _execute_sql(catalog: str, sql: str) -> None:
    """Execute SQL on Databricks via the SQL connector."""
    from databricks import sql as dbsql

    token = os.environ.get("DATABRICKS_TOKEN")
    host = os.environ.get("DATABRICKS_HOST", "adb-2235240675498194.14.azuredatabricks.net")
    http_path = os.environ.get("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/cd3a01c18e0d7516")

    if not token:
        raise ValueError("DATABRICKS_TOKEN env var required")

    with dbsql.connect(
        server_hostname=host,
        http_path=http_path,
        access_token=token,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"USE CATALOG {catalog}")
            cursor.execute(sql)


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
