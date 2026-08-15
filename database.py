"""
Database — MySQL connection and schema management for the investigation platform.

This module owns every table that belongs to our platform (as opposed to
the Wazuh Indexer, Suricata, etc., which are external data sources).

Usage:
    from database import Database

    db = Database()              # reads connection settings from .env
    db.init_tables()             # creates tables if they don't exist
    db.close()

All tables use CHAR(36) UUIDs as primary keys so records are easy to
reference across services.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import mysql.connector
from mysql.connector import Error as MySQLError


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
]


class Database:
    """Manages the MySQL connection and provides simple query helpers.

    Reads connection parameters from environment variables (loaded via
    python-dotenv elsewhere or passed explicitly).
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "987654321GO",
        database: str = "cyber_copilot",
    ) -> None:
        self._config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }
        self._conn: Optional[mysql.connector.MySQLConnection] = None

    # ── connection management ───────────────────────────────────────────

    def connect(self) -> None:
        """Open a connection to MySQL.

        The target database is created automatically if it doesn't exist.
        """
        db_name = self._config.pop("database")

        try:
            # Connect without selecting a database first.
            self._conn = mysql.connector.connect(**self._config)
            cursor = self._conn.cursor()
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}`"
            )
            cursor.close()
            self._conn.database = db_name
        except MySQLError as exc:
            raise ConnectionError(
                f"Could not connect to MySQL at "
                f"{self._config['host']}:{self._config['port']}: {exc}"
            ) from exc
        finally:
            # Restore config so connect() is idempotent.
            self._config["database"] = db_name

    def close(self) -> None:
        """Close the MySQL connection if open."""
        if self._conn and self._conn.is_connected():
            self._conn.close()
            self._conn = None

    @property
    def connection(self) -> mysql.connector.MySQLConnection:
        """Return the active connection, reconnecting if necessary."""
        if self._conn is None or not self._conn.is_connected():
            self.connect()
        return self._conn  # type: ignore[return-value]

    # ── schema management ───────────────────────────────────────────────

    def init_tables(self) -> None:
        """Create all platform tables if they don't already exist."""
        cursor = self.connection.cursor()
        for _name, ddl in _TABLES:
            cursor.execute(ddl)
        self.connection.commit()
        cursor.close()

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
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        if commit:
            self.connection.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected

    def fetchone(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> Optional[dict[str, Any]]:
        """Execute a SELECT and return the first row as a dict (or None)."""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(query, params)
        row = cursor.fetchone()
        cursor.close()
        return row

    def fetchall(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> list[dict[str, Any]]:
        """Execute a SELECT and return all rows as a list of dicts."""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows


# ── helpers ─────────────────────────────────────────────────────────────

def new_id() -> str:
    """Generate a new UUID string for use as a primary key."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return the current UTC time (timezone-aware)."""
    return datetime.now(tz=timezone.utc)
