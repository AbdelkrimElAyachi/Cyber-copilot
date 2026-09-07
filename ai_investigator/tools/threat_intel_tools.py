"""External threat-intelligence lookups for the AI Investigator/chatbot.

Deliberately a single outbound HTTP GET per IP, no local reputation
database or ML model to load — that's what keeps this tool fast and
memory-light. AbuseIPDB was picked because its "check" endpoint is exactly
one request/response with everything an analyst needs already summarised
server-side (an abuse confidence score, not raw report text to parse).
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests

from .base import Tool

_ABUSEIPDB_URL = "https://api.abuseipdb.com/api/v2/check"
_REQUEST_TIMEOUT = 8  # seconds — fail fast rather than stall the investigation
_CACHE_TTL = 3600  # seconds — an IP's reputation doesn't change minute to minute


class CheckIPReputationTool(Tool):
    """Look up an IP address's abuse/reputation history via AbuseIPDB.

    One HTTP request, one response, no heavy client library or local
    dataset — results for the same IP are cached in-process for an hour
    so repeated checks (common across investigations that share an
    attacker IP) don't spend extra quota or latency.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.getenv("ABUSEIPDB_API_KEY")
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @property
    def name(self) -> str:
        return "check_ip_reputation"

    @property
    def description(self) -> str:
        return (
            "Check whether an IP address is known-malicious via AbuseIPDB's "
            "threat intelligence database. Returns an abuse confidence score "
            "(0-100), report count, country, and ISP. Use this on suspicious "
            "source/destination IPs found in alerts — a public IP with a "
            "high score has been reported by other networks for attacks."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ip_address": {
                    "type": "string",
                    "description": "The IPv4 or IPv6 address to check.",
                },
            },
            "required": ["ip_address"],
        }

    def execute(self, **kwargs: Any) -> Any:
        ip = (kwargs.get("ip_address") or "").strip()
        if not ip:
            return {"error": "ip_address is required"}

        if not self._api_key:
            return {
                "error": (
                    "ABUSEIPDB_API_KEY is not configured — IP reputation "
                    "lookups are disabled. Ask an admin to set it."
                )
            }

        cached = self._cache.get(ip)
        if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
            return {**cached[1], "cached": True}

        # Private/reserved IPs aren't in any public reputation database and
        # just waste the request — say so instead of calling out.
        if _is_private_ip(ip):
            result = {
                "ip_address": ip,
                "is_public": False,
                "note": "Private/internal IP address — not checked against "
                "external threat intelligence.",
            }
            self._cache[ip] = (time.monotonic(), result)
            return result

        try:
            resp = requests.get(
                _ABUSEIPDB_URL,
                headers={"Key": self._api_key, "Accept": "application/json"},
                params={"ipAddress": ip, "maxAgeInDays": 90},
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            return {"error": f"IP reputation lookup failed: {e}"}

        if resp.status_code == 429:
            return {"error": "IP reputation lookup rate-limited — try again later."}
        if not resp.ok:
            return {"error": f"IP reputation lookup failed: HTTP {resp.status_code}"}

        try:
            data = resp.json().get("data", {})
        except ValueError:
            return {"error": "IP reputation lookup returned an unparseable response."}

        score = data.get("abuseConfidenceScore", 0)
        result = {
            "ip_address": data.get("ipAddress", ip),
            "is_public": data.get("isPublic"),
            "abuse_confidence_score": score,
            "verdict": (
                "malicious" if score >= 75 else
                "suspicious" if score >= 25 else
                "clean"
            ),
            "total_reports": data.get("totalReports", 0),
            "distinct_reporters": data.get("numDistinctUsers", 0),
            "country": data.get("countryCode"),
            "isp": data.get("isp"),
            "domain": data.get("domain"),
            "usage_type": data.get("usageType"),
            "is_tor": data.get("isTor"),
            "last_reported_at": data.get("lastReportedAt"),
        }
        self._cache[ip] = (time.monotonic(), result)
        return result


def _is_private_ip(ip: str) -> bool:
    """Cheap check for RFC1918/loopback/link-local — no external calls."""
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local
