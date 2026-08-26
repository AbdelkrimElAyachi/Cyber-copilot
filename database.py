"""
Database — MySQL connection pool and schema management for the investigation platform.

Uses SQLAlchemy's connection pool for thread-safe database access.
Each query gets its own connection from the pool, uses it, and returns it.
This is safe to use from FastAPI's multi-threaded request handlers.

Usage:
    from database import Database

    db = Database()              # reads connection settings from .env
    db.connect()                 # creates the engine + pool
    db.init_tables()             # creates tables if they don't exist
    db.close()                   # disposes the pool

All tables use CHAR(36) UUIDs as primary keys so records are easy to
reference across services.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# ── Schema ──────────────────────────────────────────────────────────────
# Each entry is a (table_name, create_statement) pair.
# Add new tables here — init_tables() will pick them up automatically.

_TABLES: list[tuple[str, str]] = [
    (
        "users",
        """
        CREATE TABLE IF NOT EXISTS users (
            id          CHAR(36)     PRIMARY KEY,
            username    VARCHAR(100) NOT NULL UNIQUE,
            email       VARCHAR(255) NOT NULL UNIQUE,
            full_name   VARCHAR(255),
            role        VARCHAR(50)  NOT NULL DEFAULT 'analyst',
            is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "assets",
        """
        CREATE TABLE IF NOT EXISTS assets (
            id          CHAR(36)     PRIMARY KEY,
            hostname    VARCHAR(255) NOT NULL,
            ip_address  VARCHAR(45),
            asset_type  VARCHAR(50)  NOT NULL DEFAULT 'endpoint',
            os          VARCHAR(100),
            wazuh_agent_id VARCHAR(20),
            criticality VARCHAR(20)  NOT NULL DEFAULT 'medium',
            notes       TEXT,
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_hostname  (hostname),
            INDEX idx_ip        (ip_address),
            INDEX idx_agent     (wazuh_agent_id)
        )
        """,
    ),
    (
        "investigation_policies",
        """
        CREATE TABLE IF NOT EXISTS investigation_policies (
            id          CHAR(36)     PRIMARY KEY,
            name        VARCHAR(255) NOT NULL UNIQUE,
            description TEXT,
            is_enabled  BOOLEAN      NOT NULL DEFAULT TRUE,
            priority    INT          NOT NULL DEFAULT 0,
            conditions  JSON         NOT NULL,
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_enabled (is_enabled)
        )
        """,
    ),
    (
        "investigations",
        """
        CREATE TABLE IF NOT EXISTS investigations (
            id          CHAR(36)     PRIMARY KEY,
            alert_id    VARCHAR(255) UNIQUE,
            policy_id   CHAR(36),
            title       VARCHAR(255) NOT NULL,
            description TEXT,
            status      VARCHAR(30)  NOT NULL DEFAULT 'QUEUED',
            severity    VARCHAR(20)  NOT NULL DEFAULT 'medium',
            assigned_to CHAR(36),
            created_by  CHAR(36),
            closed_at   DATETIME,
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (policy_id)   REFERENCES investigation_policies(id),
            FOREIGN KEY (assigned_to) REFERENCES users(id),
            FOREIGN KEY (created_by)  REFERENCES users(id),
            INDEX idx_status   (status),
            INDEX idx_severity (severity),
            INDEX idx_alert_id (alert_id)
        )
        """,
    ),
    (
        "investigation_evidence",
        """
        CREATE TABLE IF NOT EXISTS investigation_evidence (
            id                CHAR(36)     PRIMARY KEY,
            investigation_id  CHAR(36)     NOT NULL,
            source_type       VARCHAR(50)  NOT NULL,
            source_id         VARCHAR(255),
            data              JSON,
            notes             TEXT,
            collected_by      CHAR(36),
            created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigation_id) REFERENCES investigations(id),
            FOREIGN KEY (collected_by)     REFERENCES users(id),
            INDEX idx_investigation (investigation_id),
            INDEX idx_source        (source_type, source_id)
        )
        """,
    ),
    (
        "investigation_analysis",
        """
        CREATE TABLE IF NOT EXISTS investigation_analysis (
            id                CHAR(36)     PRIMARY KEY,
            investigation_id  CHAR(36)     NOT NULL,
            analysis_type     VARCHAR(50)  NOT NULL DEFAULT 'ai',
            verdict           VARCHAR(30),
            content           TEXT         NOT NULL,
            confidence        FLOAT,
            model_id          VARCHAR(100),
            created_by        CHAR(36),
            created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigation_id) REFERENCES investigations(id),
            FOREIGN KEY (created_by)       REFERENCES users(id),
            INDEX idx_investigation (investigation_id)
        )
        """,
    ),
    (
        "investigation_actions",
        """
        CREATE TABLE IF NOT EXISTS investigation_actions (
            id                CHAR(36)     PRIMARY KEY,
            investigation_id  CHAR(36)     NOT NULL,
            action_type       VARCHAR(50)  NOT NULL,
            description       TEXT         NOT NULL,
            reasoning         TEXT,
            status            VARCHAR(30)  NOT NULL DEFAULT 'pending',
            result            TEXT,
            performed_by      CHAR(36),
            created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at      DATETIME,
            FOREIGN KEY (investigation_id) REFERENCES investigations(id),
            FOREIGN KEY (performed_by)     REFERENCES users(id),
            INDEX idx_investigation (investigation_id),
            INDEX idx_status        (status)
        )
        """,
    ),
    (
        "poller_state",
        """
        CREATE TABLE IF NOT EXISTS poller_state (
            id              CHAR(36)     PRIMARY KEY,
            poller_name     VARCHAR(100) NOT NULL UNIQUE,
            last_timestamp  VARCHAR(50),
            last_run_at     DATETIME,
            status          VARCHAR(30)  NOT NULL DEFAULT 'idle',
            alerts_fetched  INT          NOT NULL DEFAULT 0,
            investigations_created INT   NOT NULL DEFAULT 0,
            total_runs      INT          NOT NULL DEFAULT 0,
            total_created   INT          NOT NULL DEFAULT 0,
            interval_seconds INT         NOT NULL DEFAULT 60,
            lookback_hours  INT          NOT NULL DEFAULT 24,
            error_message   TEXT,
            created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP
        )
        """,
    ),
]


class Database:
    """Thread-safe MySQL database access using SQLAlchemy's connection pool.

    Each query method gets its own connection from the pool, uses it,
    and returns it when done. Safe for concurrent use from multiple threads.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "987654321GO",
        database: str = "cyber_copilot",
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._engine: Optional[Engine] = None

    def _make_url(self, database: str = "") -> str:
        """Build a SQLAlchemy connection URL."""
        pwd = quote_plus(self._password)
        db = f"/{database}" if database else ""
        return f"mysql+pymysql://{self._user}:{pwd}@{self._host}:{self._port}{db}"

    # ── connection management ───────────────────────────────────────────

    def connect(self) -> None:
        """Create the connection pool engine.

        The target database is created automatically if it doesn't exist.
        """
        # Bound how long a connection attempt / individual query can block
        # for. Without this, a stuck connection or a lock wait blocks the
        # caller indefinitely — no exception, nothing to catch — which for
        # the AI Investigator means a background investigation can hang at
        # IN_PROGRESS forever instead of surfacing a normal, recoverable
        # error.
        _connect_args = {"connect_timeout": 10, "read_timeout": 30, "write_timeout": 30}

        # First, connect without a database to ensure it exists.
        bootstrap_engine = create_engine(
            self._make_url(), pool_pre_ping=True, connect_args=_connect_args
        )
        with bootstrap_engine.connect() as conn:
            conn.exec_driver_sql(
                f"CREATE DATABASE IF NOT EXISTS `{self._database}`"
            )
            conn.commit()
        bootstrap_engine.dispose()

        # Now create the real pooled engine.
        self._engine = create_engine(
            self._make_url(self._database),
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            pool_pre_ping=True,
            connect_args=_connect_args,
        )

    def close(self) -> None:
        """Dispose the connection pool."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    @property
    def engine(self) -> Engine:
        """Return the SQLAlchemy engine, connecting if necessary."""
        if self._engine is None:
            self.connect()
        return self._engine  # type: ignore[return-value]

    # ── schema management ───────────────────────────────────────────────

    def init_tables(self) -> None:
        """Create all platform tables if they don't already exist."""
        with self.engine.connect() as conn:
            for _name, ddl in _TABLES:
                conn.exec_driver_sql(ddl)
            # Migrate: add config columns to poller_state if missing.
            for table, col, defn in [
                ("poller_state", "interval_seconds", "INT NOT NULL DEFAULT 60"),
                ("poller_state", "lookback_hours", "INT NOT NULL DEFAULT 24"),
                ("investigation_analysis", "verdict", "VARCHAR(30)"),
                ("investigation_actions", "reasoning", "TEXT"),
            ]:
                try:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {col} {defn}"
                    )
                except Exception:
                    pass  # Column already exists.
            conn.commit()

    # ── query helpers ───────────────────────────────────────────────────

    def execute(
        self,
        query: str,
        params: Optional[tuple] = None,
        *,
        commit: bool = True,
    ) -> int:
        """Execute a write query (INSERT / UPDATE / DELETE).

        Returns the number of affected rows.
        """
        with self.engine.connect() as conn:
            result = conn.exec_driver_sql(query, params or ())
            if commit:
                conn.commit()
            return result.rowcount

    def fetchone(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> Optional[dict[str, Any]]:
        """Execute a SELECT and return the first row as a dict (or None)."""
        with self.engine.connect() as conn:
            result = conn.exec_driver_sql(query, params or ())
            row = result.fetchone()
            return dict(row._mapping) if row else None

    def fetchall(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> list[dict[str, Any]]:
        """Execute a SELECT and return all rows as a list of dicts."""
        with self.engine.connect() as conn:
            result = conn.exec_driver_sql(query, params or ())
            return [dict(row._mapping) for row in result.fetchall()]


# ── helpers ─────────────────────────────────────────────────────────────

def new_id() -> str:
    """Generate a new UUID string for use as a primary key."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return the current UTC time (timezone-aware)."""
    return datetime.now(tz=timezone.utc)
