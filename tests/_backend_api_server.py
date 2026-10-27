"""In-memory testing-service for the backend API settings and batch creation routes."""

import json
from typing import Any

import httpx

APP_ID = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
DESK = "https://desk.example.com/functions/v1/backend-desk"
NOTES = {"id": "5d0c6f1e-0000-4000-8000-000000000001", "name": "desk-notes", "description": "x"}
OTHER = {"id": "5d0c6f1e-0000-4000-8000-000000000002", "name": "desk-admin", "description": "y"}


class FakeBackendApi:
    def __init__(self) -> None:
        self.vault = {"BACKEND_DESK_API_KEY", "ADMIN_TOKEN"}
        self.skills = [NOTES, OTHER]
        self.saved: dict[str, Any] = {
            "enabled": True,
            "baseUrl": DESK,
            "openapiUrl": f"{DESK}/openapi.json",
            "authenticationSecretNames": ["BACKEND_DESK_API_KEY"],
            "skillId": NOTES["id"],
        }
        self.puts: list[dict[str, Any]] = []
        self.batches: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        base = f"/api/v1/apps/{APP_ID}"
        path, method = request.url.path, request.method
        if path == f"{base}/backend-config" and method == "GET":
            return httpx.Response(200, json=self.view())
        if path == f"{base}/backend-config" and method == "PUT":
            return self.put(json.loads(request.content))
        if path.startswith(f"{base}/skills/"):
            ref = path.rsplit("/", 1)[1]
            skill = next((s for s in self.skills if ref in (s["id"], s["name"])), None)
            if skill is None:
                return httpx.Response(404, json={"message": f"Skill '{ref}' not found"})
            return httpx.Response(200, json=skill)
        if path == f"{base}/batches" and method == "POST":
            return self.create_batch(json.loads(request.content))
        return httpx.Response(404, json={"detail": f"unexpected {method} {path}"})

    def put(self, body: dict[str, Any]) -> httpx.Response:
        self.puts.append(body)
        for url in (body["baseUrl"], body["openapiUrl"]):
            if url and "169.254" in url:
                reason = "it points at a private or reserved address"
                return _rejected(f"{url} cannot be used as a backend URL: {reason}")
        if body["enabled"] and not (body["baseUrl"] and body["openapiUrl"]):
            return _rejected("Turning the backend API on needs a base URL and an OpenAPI URL")
        self.saved = body
        return httpx.Response(200, json=self.view())

    def create_batch(self, body: dict[str, Any]) -> httpx.Response:
        self.batches.append(body)
        override = body.get("backendApiOverride") or {}
        if any("169.254" in (url or "") for url in override.values()):
            return _rejected("http://169.254.169.254 cannot be used as a backend URL")
        return httpx.Response(201, json=_batch(body))

    def view(self) -> dict[str, Any]:
        names = self.saved["authenticationSecretNames"]
        skill = next((s for s in self.skills if s["id"] == self.saved["skillId"]), None)
        return {
            "enabled": self.saved["enabled"],
            "baseUrl": self.saved["baseUrl"],
            "openapiUrl": self.saved["openapiUrl"],
            "authenticationSecretNames": names,
            "missingSecretNames": [n for n in names if n not in self.vault],
            "skill": skill,
        }


def _rejected(message: str) -> httpx.Response:
    return httpx.Response(422, json={"error": "unprocessable", "message": message, "details": {}})


def _batch(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "2e20026b-04c4-4a5f-b6f0-aa4b5207e3e3",
        "appId": APP_ID,
        "tenantId": "92a7a284-7c32-41f4-bb79-2e1a95c69c5a",
        "source": "cli",
        "status": "pending",
        "commitSha": body.get("commitSha"),
        "createdAt": "2026-10-27T10:00:00Z",
        "targets": [],
        "storyRuns": [],
    }
