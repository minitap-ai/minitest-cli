"""In-memory testing-service for the per-app network settings routes."""

import json
from typing import Any

import httpx

APP_ID = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
DOMAIN_PATTERN = r"^(\*\.)?([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z]([a-z0-9-]{0,61}[a-z0-9])?$"
MAC_MINI = {
    "id": "c0000000-0000-0000-0000-000000000001",
    "name": "QA Mac mini",
    "status": "online",
    "domains": ["*.pnqa.internal"],
    "ports": [443],
    "lastSeenAt": "2026-10-14T09:00:00Z",
}
LAPTOP = {
    "id": "c0000000-0000-0000-0000-000000000002",
    "name": "Laptop",
    "status": "offline",
    "domains": [],
    "ports": [],
    "lastSeenAt": None,
}


def _covers(selector: str, domain: str) -> bool:
    if selector == domain:
        return True
    host = domain[2:] if domain.startswith("*.") else domain
    return selector.startswith("*.") and host.endswith(selector[1:])


class FakeNetworkSettings:
    def __init__(self) -> None:
        self.role_allows_writes = True
        self.available = True
        self.connectors: list[dict[str, Any]] = [MAC_MINI, LAPTOP]
        self.proxy: dict[str, Any] = {
            "enabled": True,
            "country": "tr",
            "allowedDomains": ["ipinfo.io"],
        }
        self.network: dict[str, Any] = {
            "enabled": True,
            "connectorId": MAC_MINI["id"],
            "domains": ["web.stg.pnqa.internal"],
            "ports": [443],
        }
        self.puts: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        base = f"/api/v1/apps/{APP_ID}"
        path, method = request.url.path, request.method
        if method == "PUT" and not self.role_allows_writes:
            detail = "Changing this app setting requires the OWNER or ADMIN role"
            return httpx.Response(403, json={"detail": detail})
        if path == f"{base}/residential-proxy":
            if method == "PUT":
                self.proxy = self._record(request)
            return httpx.Response(200, json=self.proxy_view())
        if path == f"{base}/private-network":
            if method == "PUT":
                self.network = self._record(request)
            return httpx.Response(200, json=self.network_view())
        if path == f"{base}/private-network/connectors":
            return httpx.Response(
                200, json={"available": self.available, "connectors": self.connectors}
            )
        return httpx.Response(404, json={"detail": f"unexpected {method} {path}"})

    def _record(self, request: httpx.Request) -> dict[str, Any]:
        body = json.loads(request.content)
        self.puts.append(body)
        return body

    def proxy_view(self) -> dict[str, Any]:
        return {
            **self.proxy,
            "available": self.available,
            "availableCountries": ["tr", "fr", "de", "gb", "us"],
            "domainPattern": DOMAIN_PATTERN,
            "maxDomains": 3,
            "usdPerGb": "4.50",
        }

    def network_view(self) -> dict[str, Any]:
        connector = next(
            (c for c in self.connectors if c["id"] == self.network["connectorId"]), None
        )
        allowlist = connector["domains"] if connector else []
        return {
            "available": self.available,
            "enabled": self.network["enabled"],
            "connector": connector and {**connector, "tokenPrefix": "mtc_abc", "instances": []},
            "domains": self.network["domains"],
            "ports": self.network["ports"],
            "domainsRefusedByConnector": [
                d
                for d in self.network["domains"]
                if connector and not any(_covers(s, d) for s in allowlist)
            ],
            "domainPattern": DOMAIN_PATTERN,
            "maxDomains": 64,
        }
