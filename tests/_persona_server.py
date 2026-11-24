"""In-memory testing-service for the persona, test-account and persona-binding routes."""

import json
import uuid
from typing import Any

import httpx

APP = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
BASE = f"/api/v1/apps/{APP}"
STORY = "3ff0cb0e-0000-4000-8000-000000000001"


def _error(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"error": "error", "message": message, "details": {}})


class FakePersonaApi:
    def __init__(self) -> None:
        self.personas: dict[str, dict[str, Any]] = {}
        self.accounts: dict[str, dict[str, Any]] = {}
        self.bindings: dict[tuple[str, str | None], list[str]] = {}
        self.secrets: dict[str, dict[str, Any]] = {}
        self.writes: list[tuple[str, str, Any]] = []

    def persona(self, name: str, *, kind: str = "standard", exclusive: bool = False) -> str:
        pid = str(uuid.uuid4())
        self.personas[pid] = {
            "id": pid,
            "name": name,
            "about": None,
            "kind": kind,
            "exclusiveUse": exclusive,
        }
        return pid

    def handle(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path.removeprefix(BASE)
        body: Any = json.loads(request.content) if request.content else None
        if method != "GET":
            self.writes.append((method, path, body))
        parts = path.strip("/").split("/")
        if parts[0] == "personas":
            return self._personas(method, parts[1:], body)
        if parts[0] == "test-accounts":
            return self._accounts(method, parts[1:], body)
        if parts[0] == "test-profiles" and method == "PATCH":
            account = self.accounts[parts[1]]
            for key in ("password", "username"):
                if key in body:
                    self.secrets.setdefault(parts[1], {})[key] = body[key]
            return httpx.Response(200, json={**self._account(account), "qaInboxShared": False})
        if parts[0] == "user-stories" and parts[2:] == ["personas"]:
            return self._story(method, parts[1], request, body)
        return _error(404, f"unexpected {method} {path}")

    def _personas(self, method: str, rest: list[str], body: Any) -> httpx.Response:
        if not rest:
            if method == "GET":
                items = sorted(self.personas.values(), key=lambda p: p["name"].casefold())
                return httpx.Response(200, json={"items": [self._view(p) for p in items]})
            if self._taken(body["name"]):
                return _error(409, f"A persona named {body['name']!r} already exists for this app.")
            pid = self.persona(body["name"], exclusive=body["exclusiveUse"])
            self.personas[pid]["about"] = body["about"]
            return httpx.Response(201, json=self._view(self.personas[pid]))
        persona = self.personas.get(rest[0])
        if persona is None:
            return _error(404, f"Persona {rest[0]} not found.")
        tail = rest[1:]
        if tail == ["pool"]:
            entries = [
                {
                    "account": self._account(a),
                    "state": a["state"],
                    "holderCount": len(a.get("holders", [])),
                    "holders": a.get("holders", []),
                }
                for a in self._accounts_of(persona["id"])
            ]
            return httpx.Response(200, json={"persona": self._view(persona), "accounts": entries})
        if tail == ["accounts"]:
            return self._add_account(persona, body)
        if tail == ["exclusive-use"]:
            if persona["kind"] == "new_user" and body["exclusiveUse"]:
                return _error(422, "The New user persona cannot be marked for exclusive use.")
            persona["exclusiveUse"] = body["exclusiveUse"]
            return httpx.Response(200, json=self._view(persona))
        if method == "PATCH":
            persona.update(body)
            return httpx.Response(200, json=self._view(persona))
        if method == "DELETE":
            if any(persona["id"] in ids for ids in self.bindings.values()):
                return _error(409, f"Persona {persona['id']} is still bound to 1 scenario(s).")
            if self._accounts_of(persona["id"]):
                return _error(409, f"Persona {persona['id']} still has test account(s).")
            del self.personas[persona["id"]]
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={
                **self._view(persona),
                "accounts": [self._account(a) for a in self._accounts_of(persona["id"])],
            },
        )

    def _add_account(self, persona: dict[str, Any], body: dict[str, Any]) -> httpx.Response:
        aid = str(uuid.uuid4())
        count = len(self._accounts_of(persona["id"]))
        name = body.get("name") or (
            persona["name"] if count == 0 else f"{persona['name']} {count + 1}"
        )
        self.accounts[aid] = {
            "id": aid,
            "personaId": persona["id"],
            "name": name,
            "username": body.get("username"),
            "state": "free",
            "cooldownUntil": None,
            "cooldownReason": None,
        }
        self.secrets[aid] = {k: v for k, v in body.items() if k in ("password", "staticOtpCode")}
        return httpx.Response(201, json=self._account(self.accounts[aid]))

    def _accounts(self, method: str, rest: list[str], body: Any) -> httpx.Response:
        account = self.accounts.get(rest[0])
        if account is None:
            return _error(404, f"Test account {rest[0]} not found.")
        if rest[1:] == ["persona"]:
            account["personaId"] = body["personaId"]
        elif rest[1:] == ["cooldown"]:
            account.update(state="free", cooldownUntil=None, cooldownReason=None)
        else:
            del self.accounts[account["id"]]
            return httpx.Response(204)
        return httpx.Response(200, json=self._account(account))

    def _story(self, method: str, story: str, request: httpx.Request, body: Any) -> httpx.Response:
        draft = body["draftFeatureId"] if body else request.url.params.get("draftFeatureId")
        if method == "PUT":
            self.bindings[(story, draft)] = body["personaIds"]
        ids = self.bindings.get((story, draft), [])
        items = [
            {
                "id": p,
                "name": self.personas[p]["name"],
                "kind": "standard",
                "exclusiveUse": self.personas[p]["exclusiveUse"],
            }
            for p in ids
        ]
        return httpx.Response(
            200, json={"userStoryId": story, "draftFeatureId": draft, "items": items}
        )

    def _taken(self, name: str) -> bool:
        return any(p["name"].casefold() == name.casefold() for p in self.personas.values())

    def _accounts_of(self, persona_id: str) -> list[dict[str, Any]]:
        return [a for a in self.accounts.values() if a["personaId"] == persona_id]

    def _view(self, persona: dict[str, Any]) -> dict[str, Any]:
        states = [a["state"] for a in self._accounts_of(persona["id"])]
        return {
            **persona,
            "accountCount": len(states),
            "freeCount": states.count("free"),
            "inUseCount": states.count("in_use"),
            "coolingDownCount": states.count("cooling_down"),
            "scenarioCount": 0,
        }

    def _account(self, account: dict[str, Any]) -> dict[str, Any]:
        held = self.secrets.get(account["id"], {})
        hidden = ("state", "holders")
        return {key: value for key, value in account.items() if key not in hidden} | {
            "hasPassword": "password" in held,
            "hasStaticOtpCode": "staticOtpCode" in held,
            "hasTestCard": False,
        }
