"""
Alert Receiver — retrieves alerts from the Wazuh Indexer.

This module provides a single class, `AlertReceiver`, that hides all
OpenSearch query details behind a clean Python interface.

Usage:
    from alert_receiver import AlertReceiver

    receiver = AlertReceiver(
        host="192.168.1.100",
        port=9200,
        username="admin",
        password="changeme",
    )
    alerts = receiver.get_alerts(agent_id="001", min_level=10, limit=50)
"""

from datetime import datetime, timezone
from typing import Any, Optional

from opensearchpy import OpenSearch


# ── Wazuh 4.14.x index pattern ─────────────────────────────────────────
# Alerts are stored in daily indices that match this pattern.
WAZUH_ALERTS_INDEX = "wazuh-alerts-4.x-*"


class AlertReceiver:
    """Connects to the Wazuh Indexer and retrieves alerts with simple filters.

    All query‑building logic lives inside this class so the rest of the
    application never has to know how OpenSearch queries work.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9200,
        username: str = "admin",
        password: str = "admin",
        verify_ssl: bool = False,
        index_pattern: str = WAZUH_ALERTS_INDEX,
    ) -> None:
        """Create a new AlertReceiver.

        Args:
            host:          Wazuh Indexer hostname or IP.
            port:          Wazuh Indexer port (default 9200).
            username:      Indexer username.
            password:      Indexer password.
            verify_ssl:    Verify TLS certificates (disable for self‑signed).
            index_pattern: Override the default alert index pattern if needed.
        """
        self._client = OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_auth=(username, password),
            use_ssl=True,
            verify_certs=verify_ssl,
            ssl_show_warn=False,
        )
        self._index = index_pattern

    # ── public API ──────────────────────────────────────────────────────

    def get_alerts(
        self,
        *,
        # time range
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        # agent
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        # rule
        rule_id: Optional[str] = None,
        min_level: Optional[int] = None,
        max_level: Optional[int] = None,
        rule_group: Optional[str] = None,
        # network / user
        source_ip: Optional[str] = None,
        destination_ip: Optional[str] = None,
        src_user: Optional[str] = None,
        dst_user: Optional[str] = None,
        # manager
        manager_name: Optional[str] = None,
        # free‑text
        search_text: Optional[str] = None,
        # pagination / sorting
        limit: int = 100,
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        """Retrieve alerts from the Wazuh Indexer.

        Every parameter is optional.  When multiple filters are given they
        are combined with AND logic (all must match).

        Args:
            from_time:      Only alerts **after** this datetime.
            to_time:        Only alerts **before** this datetime.
            agent_id:       Wazuh agent ID  (e.g. "001").
            agent_name:     Wazuh agent name (e.g. "web-server-01").
            rule_id:        Wazuh rule ID   (e.g. "5710").
            min_level:      Minimum rule level (inclusive, 1‑16).
            max_level:      Maximum rule level (inclusive, 1‑16).
            rule_group:     Rule group name  (e.g. "authentication_failed").
            source_ip:      Source IP extracted by decoders (data.srcip).
            destination_ip: Destination IP   (data.dstip).
            src_user:       Source user       (data.srcuser).
            dst_user:       Destination user  (data.dstuser).
            manager_name:   Wazuh manager that generated the alert.
            search_text:    Free‑text search across the full_log field.
            limit:          Maximum number of alerts to return (default 100).
            sort_order:     "desc" (newest first) or "asc" (oldest first).

        Returns:
            A list of alert dicts (each is the raw ``_source`` document).
        """
        query = self._build_query(
            from_time=from_time,
            to_time=to_time,
            agent_id=agent_id,
            agent_name=agent_name,
            rule_id=rule_id,
            min_level=min_level,
            max_level=max_level,
            rule_group=rule_group,
            source_ip=source_ip,
            destination_ip=destination_ip,
            src_user=src_user,
            dst_user=dst_user,
            manager_name=manager_name,
            search_text=search_text,
        )

        body: dict[str, Any] = {
            "size": min(limit, 10_000),  # OpenSearch hard cap
            "query": query,
            "sort": [{"timestamp": {"order": sort_order}}],
        }

        response = self._client.search(index=self._index, body=body)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    def count_alerts(self, **filters: Any) -> int:
        """Return the total number of alerts matching the given filters.

        Accepts the same keyword arguments as ``get_alerts`` (except
        ``limit`` and ``sort_order``).
        """
        filters.pop("limit", None)
        filters.pop("sort_order", None)
        query = self._build_query(**filters)
        response = self._client.count(index=self._index, body={"query": query})
        return response["count"]

    def get_alert_by_id(self, alert_id: str) -> Optional[dict[str, Any]]:
        """Fetch a single alert by its OpenSearch document ``_id``.

        Returns ``None`` if the alert is not found.
        """
        try:
            response = self._client.get(index=self._index, id=alert_id)
            return response["_source"]
        except Exception:
            return None

    # ── query builder (private) ─────────────────────────────────────────

    @staticmethod
    def _build_query(
        *,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        rule_id: Optional[str] = None,
        min_level: Optional[int] = None,
        max_level: Optional[int] = None,
        rule_group: Optional[str] = None,
        source_ip: Optional[str] = None,
        destination_ip: Optional[str] = None,
        src_user: Optional[str] = None,
        dst_user: Optional[str] = None,
        manager_name: Optional[str] = None,
        search_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """Translate keyword filters into an OpenSearch ``bool`` query.

        ┌─────────────────┬──────────────────────────────────┐
        │ Python param    │ Wazuh alert field                │
        ├─────────────────┼──────────────────────────────────┤
        │ from_time       │ timestamp  (range gte)           │
        │ to_time         │ timestamp  (range lte)           │
        │ agent_id        │ agent.id                         │
        │ agent_name      │ agent.name                       │
        │ rule_id         │ rule.id                          │
        │ min_level       │ rule.level (range gte)           │
        │ max_level       │ rule.level (range lte)           │
        │ rule_group      │ rule.groups                      │
        │ source_ip       │ data.srcip                       │
        │ destination_ip  │ data.dstip                       │
        │ src_user        │ data.srcuser                     │
        │ dst_user        │ data.dstuser                     │
        │ manager_name    │ manager.name                     │
        │ search_text     │ full_log   (match query)         │
        └─────────────────┴──────────────────────────────────┘
        """
        filters: list[dict[str, Any]] = []

        # ── time range ──────────────────────────────────────────────
        time_range: dict[str, str] = {}
        if from_time is not None:
            time_range["gte"] = _to_iso(from_time)
        if to_time is not None:
            time_range["lte"] = _to_iso(to_time)
        if time_range:
            filters.append({"range": {"timestamp": time_range}})

        # ── exact‑match filters (term queries) ──────────────────────
        _term_fields = {
            "agent.id": agent_id,
            "agent.name": agent_name,
            "rule.id": rule_id,
            "rule.groups": rule_group,
            "data.srcip": source_ip,
            "data.dstip": destination_ip,
            "data.srcuser": src_user,
            "data.dstuser": dst_user,
            "manager.name": manager_name,
        }
        for field, value in _term_fields.items():
            if value is not None:
                filters.append({"term": {field: value}})

        # ── rule.level range ────────────────────────────────────────
        level_range: dict[str, int] = {}
        if min_level is not None:
            level_range["gte"] = min_level
        if max_level is not None:
            level_range["lte"] = max_level
        if level_range:
            filters.append({"range": {"rule.level": level_range}})

        # ── free‑text search ────────────────────────────────────────
        if search_text is not None:
            filters.append({"match": {"full_log": search_text}})

        # If no filters were given, match everything.
        if not filters:
            return {"match_all": {}}

        return {"bool": {"filter": filters}}

    # ── connection check ────────────────────────────────────────────────

    def ping(self) -> bool:
        """Return ``True`` if the Wazuh Indexer is reachable."""
        return self._client.ping()


# ── helpers ─────────────────────────────────────────────────────────────

def _to_iso(dt: datetime) -> str:
    """Convert a datetime to an ISO‑8601 string in UTC.

    If the datetime is naive (no timezone), it is assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()
