"""Platform database tools for the AI Investigator."""

from __future__ import annotations

from datetime import datetime, date
from typing import Any, Optional

from database import Database
from .base import Tool


def _serialise_row(row: Optional[dict]) -> Optional[dict]:
    """Convert datetime objects in a row dict to ISO strings for JSON."""
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, date):
            out[k] = v.isoformat()
        elif isinstance(v, bytes):
            out[k] = v.decode("utf-8", errors="replace")
        else:
            out[k] = v
    return out


def _serialise_rows(rows: list[dict]) -> list[dict]:
    return [_serialise_row(r) for r in rows]  # type: ignore[misc]


# ── Investigation tools ─────────────────────────────────────────────────


class SearchInvestigationsTool(Tool):
    """Search existing investigations in the platform."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def name(self) -> str:
        return "search_investigations"

    @property
    def description(self) -> str:
        return (
            "Search existing investigations in the platform database. "
            "Useful to find related or similar past investigations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["QUEUED", "IN_PROGRESS", "COMPLETED", "CLOSED"],
                    "description": "Filter by investigation status.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Filter by severity.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10).",
                },
            },
            "required": [],
        }

    def execute(self, **kwargs: Any) -> Any:
        try:
            conditions = []
            params: list[Any] = []

            if kwargs.get("status"):
                conditions.append("status = %s")
                params.append(kwargs["status"])
            if kwargs.get("severity"):
                conditions.append("severity = %s")
                params.append(kwargs["severity"])

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            limit = min(kwargs.get("limit", 10), 50)

            rows = self._db.fetchall(
                f"SELECT id, alert_id, title, status, severity, created_at "
                f"FROM investigations {where} "
                f"ORDER BY created_at DESC LIMIT %s",
                tuple(params) + (limit,),
            )
            return {"count": len(rows), "investigations": _serialise_rows(rows)}
        except Exception as e:
            return {"error": str(e)}


class GetInvestigationTool(Tool):
    """Get full details of an investigation."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def name(self) -> str:
        return "get_investigation"

    @property
    def description(self) -> str:
        return "Get full details of a specific investigation by its ID."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "investigation_id": {
                    "type": "string",
                    "description": "The investigation UUID.",
                },
            },
            "required": ["investigation_id"],
        }

    def execute(self, **kwargs: Any) -> Any:
        inv_id = kwargs.get("investigation_id", "")
        if not inv_id:
            return {"error": "investigation_id is required"}
        try:
            row = self._db.fetchone(
                "SELECT id, alert_id, policy_id, title, description, "
                "status, severity, closed_at, created_at, updated_at "
                "FROM investigations WHERE id = %s",
                (inv_id,),
            )
            if not row:
                return {"error": f"Investigation {inv_id} not found"}
            return _serialise_row(row)
        except Exception as e:
            return {"error": str(e)}


class GetInvestigationEvidenceTool(Tool):
    """Get evidence collected for an investigation."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def name(self) -> str:
        return "get_investigation_evidence"

    @property
    def description(self) -> str:
        return "Get all evidence collected for a specific investigation."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "investigation_id": {
                    "type": "string",
                    "description": "The investigation UUID.",
                },
            },
            "required": ["investigation_id"],
        }

    def execute(self, **kwargs: Any) -> Any:
        inv_id = kwargs.get("investigation_id", "")
        if not inv_id:
            return {"error": "investigation_id is required"}
        try:
            rows = self._db.fetchall(
                "SELECT id, source_type, source_id, data, notes, created_at "
                "FROM investigation_evidence WHERE investigation_id = %s "
                "ORDER BY created_at",
                (inv_id,),
            )
            return {"count": len(rows), "evidence": _serialise_rows(rows)}
        except Exception as e:
            return {"error": str(e)}


class GetInvestigationAnalysisTool(Tool):
    """Get AI analysis for an investigation."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def name(self) -> str:
        return "get_investigation_analysis"

    @property
    def description(self) -> str:
        return "Get AI analysis results for a specific investigation."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "investigation_id": {
                    "type": "string",
                    "description": "The investigation UUID.",
                },
            },
            "required": ["investigation_id"],
        }

    def execute(self, **kwargs: Any) -> Any:
        inv_id = kwargs.get("investigation_id", "")
        if not inv_id:
            return {"error": "investigation_id is required"}
        try:
            rows = self._db.fetchall(
                "SELECT id, analysis_type, verdict, content, confidence, model_id, created_at "
                "FROM investigation_analysis WHERE investigation_id = %s "
                "ORDER BY created_at",
                (inv_id,),
            )
            return {"count": len(rows), "analyses": _serialise_rows(rows)}
        except Exception as e:
            return {"error": str(e)}


# ── Asset tools ─────────────────────────────────────────────────────────


class SearchAssetsTool(Tool):
    """Search assets in the platform."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def name(self) -> str:
        return "search_assets"

    @property
    def description(self) -> str:
        return (
            "Search assets (hosts, servers, endpoints) by hostname, "
            "IP address, or Wazuh agent ID."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "hostname": {
                    "type": "string",
                    "description": "Search by hostname (partial match).",
                },
                "ip_address": {
                    "type": "string",
                    "description": "Search by IP address.",
                },
                "wazuh_agent_id": {
                    "type": "string",
                    "description": "Search by Wazuh agent ID.",
                },
            },
            "required": [],
        }

    def execute(self, **kwargs: Any) -> Any:
        try:
            conditions = []
            params: list[Any] = []

            if kwargs.get("hostname"):
                conditions.append("hostname LIKE %s")
                params.append(f"%{kwargs['hostname']}%")
            if kwargs.get("ip_address"):
                conditions.append("ip_address = %s")
                params.append(kwargs["ip_address"])
            if kwargs.get("wazuh_agent_id"):
                conditions.append("wazuh_agent_id = %s")
                params.append(kwargs["wazuh_agent_id"])

            if not conditions:
                return {"error": "At least one search parameter is required"}

            where = " AND ".join(conditions)
            rows = self._db.fetchall(
                f"SELECT id, hostname, ip_address, asset_type, os, "
                f"wazuh_agent_id, criticality, notes, created_at "
                f"FROM assets WHERE {where} LIMIT 20",
                tuple(params),
            )
            return {"count": len(rows), "assets": _serialise_rows(rows)}
        except Exception as e:
            return {"error": str(e)}


class GetAssetTool(Tool):
    """Get full details of an asset."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def name(self) -> str:
        return "get_asset"

    @property
    def description(self) -> str:
        return "Get full details of a specific asset by its ID."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "The asset UUID.",
                },
            },
            "required": ["asset_id"],
        }

    def execute(self, **kwargs: Any) -> Any:
        asset_id = kwargs.get("asset_id", "")
        if not asset_id:
            return {"error": "asset_id is required"}
        try:
            row = self._db.fetchone(
                "SELECT id, hostname, ip_address, asset_type, os, "
                "wazuh_agent_id, criticality, notes, created_at, updated_at "
                "FROM assets WHERE id = %s",
                (asset_id,),
            )
            if not row:
                return {"error": f"Asset {asset_id} not found"}
            return _serialise_row(row)
        except Exception as e:
            return {"error": str(e)}
