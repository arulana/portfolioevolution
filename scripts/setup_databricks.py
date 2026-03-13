#!/usr/bin/env python3
"""One-time setup: create Databricks catalog, schema, and Delta tables.

Reads connection details from environment variables:
    DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN
    DATABRICKS_CATALOG (default: synthetic_bank)
    DATABRICKS_SCHEMA (default: simulation)

Usage:
    python scripts/setup_databricks.py
"""

from portfolio_evolution.output.databricks_sync import DatabricksSync


def main() -> None:
    sync = DatabricksSync.from_env()
    print(f"Connecting to Databricks: {sync._host}")
    sync.ensure_tables()
    print("All tables created successfully.")
    sync.close()


if __name__ == "__main__":
    main()
