"""Databricks Delta Lake sync for the four source system tables.

Pushes system-view DataFrames from the simulation to Databricks Delta tables
via the Databricks SQL Connector. Each system maps to its own table under a
configurable catalog and schema.

Usage:
    sync = DatabricksSync.from_env()  # reads DATABRICKS_* env vars
    sync.ensure_tables()
    sync.push_system_views(run_id, sim_day, crm_df, los_df, core_df, deposits_df)

Environment variables:
    DATABRICKS_HOST       - Workspace URL (e.g., adb-123456789.12.azuredatabricks.net)
    DATABRICKS_HTTP_PATH  - SQL warehouse HTTP path
    DATABRICKS_TOKEN      - Personal access token or service principal token
    DATABRICKS_CATALOG    - Unity Catalog name (default: "synthetic_bank")
    DATABRICKS_SCHEMA     - Schema/database name (default: "simulation")
"""

from __future__ import annotations

import logging
import os
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)

_sql_connector_available = True
try:
    from databricks import sql as databricks_sql
except ImportError:
    _sql_connector_available = False
    databricks_sql = None  # type: ignore[assignment]


_TABLE_DDL: dict[str, str] = {
    "crm_pipeline": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.crm_pipeline (
            run_id STRING, sim_day INT, OPP_ID STRING,
            BORROWER_NAME STRING, STAGE STRING, EXPECTED_AMOUNT DOUBLE,
            CLOSE_PROB DOUBLE, SEGMENT STRING, RM_NAME STRING,
            RM_CODE STRING, EXPECTED_CLOSE_DATE STRING,
            LAST_ACTIVITY_DATE STRING, STATE STRING, SOURCE STRING
        ) USING DELTA
    """,
    "los_underwriting": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.los_underwriting (
            run_id STRING, sim_day INT, APP_ID STRING,
            BORROWER_NAME STRING, UW_STAGE STRING,
            REQUESTED_AMOUNT DOUBLE, APPROVED_AMOUNT DOUBLE,
            RISK_RATING STRING, RATING_NUMERIC INT,
            ANALYST_CODE STRING, APPROVAL_DATE STRING,
            EXPECTED_CLOSE_DATE STRING, RATE_TYPE STRING,
            EXPECTED_RATE DOUBLE, SEGMENT STRING, STATE STRING,
            IS_RENEWAL BOOLEAN, CONDITION_COUNT INT
        ) USING DELTA
    """,
    "core_funded": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.core_funded (
            run_id STRING, sim_day INT, ACCT_NO STRING,
            BORROWER STRING, CURRENT_BAL DOUBLE, COMMITTED_AMT DOUBLE,
            INT_RATE DOUBLE, RATE_TYPE STRING, ORIG_DATE STRING,
            MATURITY_DATE STRING, AMORT_TYPE STRING, PMT_FREQ STRING,
            RISK_RATING STRING, RISK_RATING_NUM INT,
            SEGMENT STRING, PRODUCT_TYPE STRING, STATE STRING,
            ACCRUAL_STATUS STRING, COLLATERAL_TYPE STRING,
            PROPERTY_TYPE STRING, OWNER_OCC BOOLEAN,
            SNC_FLAG BOOLEAN, TDR_FLAG BOOLEAN, AS_OF_DATE STRING
        ) USING DELTA
    """,
    "core_deposits": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.core_deposits (
            run_id STRING, sim_day INT, ACCOUNT_ID STRING,
            CUSTOMER_ID STRING, ACCOUNT_TYPE STRING,
            CURRENT_BAL DOUBLE, INT_RATE DOUBLE, RATE_TYPE STRING,
            DEPOSIT_BETA DOUBLE, OPEN_DATE STRING,
            LIQUIDITY_CLASS STRING, SEGMENT STRING, AS_OF_DATE STRING
        ) USING DELTA
    """,
}


class DatabricksSync:
    """Pushes simulation system views to Databricks Delta tables."""

    def __init__(
        self,
        host: str,
        http_path: str,
        token: str,
        catalog: str = "synthetic_bank",
        schema: str = "simulation",
    ) -> None:
        if not _sql_connector_available:
            raise RuntimeError(
                "databricks-sql-connector is not installed. "
                "Install with: pip install 'portfolio-evolution[databricks]'"
            )
        self._host = host
        self._http_path = http_path
        self._token = token
        self._catalog = catalog
        self._schema = schema
        self._conn: Any = None

    @classmethod
    def from_env(cls) -> DatabricksSync:
        """Create instance from environment variables."""
        host = os.environ.get("DATABRICKS_HOST", "")
        http_path = os.environ.get("DATABRICKS_HTTP_PATH", "")
        token = os.environ.get("DATABRICKS_TOKEN", "")
        catalog = os.environ.get("DATABRICKS_CATALOG", "synthetic_bank")
        schema = os.environ.get("DATABRICKS_SCHEMA", "simulation")

        if not host or not http_path or not token:
            raise ValueError(
                "DATABRICKS_HOST, DATABRICKS_HTTP_PATH, and DATABRICKS_TOKEN "
                "must be set as environment variables."
            )

        return cls(
            host=host,
            http_path=http_path,
            token=token,
            catalog=catalog,
            schema=schema,
        )

    def _connect(self) -> None:
        if self._conn is not None:
            return
        self._conn = databricks_sql.connect(
            server_hostname=self._host,
            http_path=self._http_path,
            access_token=self._token,
        )

    def _execute(self, sql: str) -> None:
        self._connect()
        with self._conn.cursor() as cursor:
            cursor.execute(sql)

    def ensure_tables(self) -> None:
        """Create catalog, schema, and all four system tables if they don't exist."""
        self._execute(f"CREATE CATALOG IF NOT EXISTS {self._catalog}")
        self._execute(f"CREATE SCHEMA IF NOT EXISTS {self._catalog}.{self._schema}")

        for table_name, ddl_template in _TABLE_DDL.items():
            ddl = ddl_template.format(catalog=self._catalog, schema=self._schema)
            self._execute(ddl)
            logger.info("Ensured table: %s.%s.%s", self._catalog, self._schema, table_name)

    def push_dataframe(
        self,
        table_name: str,
        df: pl.DataFrame,
        run_id: str,
        sim_day: int,
    ) -> int:
        """Push a Polars DataFrame to a Delta table via INSERT VALUES.

        Deletes existing data for the given run_id+sim_day first (idempotent),
        then inserts the new rows.

        Returns the number of rows inserted.
        """
        if df.is_empty():
            return 0

        fqn = f"{self._catalog}.{self._schema}.{table_name}"

        self._execute(
            f"DELETE FROM {fqn} WHERE run_id = '{run_id}' AND sim_day = {sim_day}"
        )

        batch = df.drop("SIM_DAY") if "SIM_DAY" in df.columns else df
        batch = batch.with_columns(
            pl.lit(run_id).alias("run_id"),
            pl.lit(sim_day).alias("sim_day"),
        )

        cols = batch.columns
        col_list = ", ".join(cols)

        rows_sql = []
        for row in batch.iter_rows():
            vals = []
            for v in row:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, bool):
                    vals.append("TRUE" if v else "FALSE")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    escaped = str(v).replace("'", "''")
                    vals.append(f"'{escaped}'")
            rows_sql.append(f"({', '.join(vals)})")

        chunk_size = 500
        total = 0
        for i in range(0, len(rows_sql), chunk_size):
            chunk = rows_sql[i : i + chunk_size]
            values_str = ",\n".join(chunk)
            self._execute(f"INSERT INTO {fqn} ({col_list}) VALUES {values_str}")
            total += len(chunk)

        logger.info("Pushed %d rows to %s (run=%s, day=%d)", total, fqn, run_id, sim_day)
        return total

    def push_system_views(
        self,
        run_id: str,
        sim_day: int,
        crm_df: pl.DataFrame | None = None,
        los_df: pl.DataFrame | None = None,
        core_df: pl.DataFrame | None = None,
        deposits_df: pl.DataFrame | None = None,
    ) -> dict[str, int]:
        """Push all four system views to Databricks. Returns row counts per table."""
        results: dict[str, int] = {}
        for table, df in [
            ("crm_pipeline", crm_df),
            ("los_underwriting", los_df),
            ("core_funded", core_df),
            ("core_deposits", deposits_df),
        ]:
            if df is not None:
                results[table] = self.push_dataframe(table, df, run_id, sim_day)
            else:
                results[table] = 0
        return results

    def close(self) -> None:
        """Close the Databricks SQL connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> DatabricksSync:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
