from __future__ import annotations

from typing import Any, Self

import httpx

BASE_URL = "https://api.eliis.eu"
COMMON_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://eliis.eu",
    "Referer": "https://eliis.eu/",
    "Accept": "application/json",
}


class EliisAuthError(Exception):
    pass


class EliisClient:
    def __init__(self) -> None:
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers=COMMON_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )

    def login(self, email: str, password: str) -> dict[str, Any]:
        response = self._http.post("/api/auth/login", json={"username": email, "password": password, "platform": "web"})
        if response.status_code != 200:  # noqa: PLR2004
            msg = f"Login failed: {response.status_code} {response.text}"
            raise EliisAuthError(msg)
        data = response.json()
        if isinstance(data, dict) and data.get("type"):
            msg = f"Login requires additional step: {data.get('type')}"
            raise EliisAuthError(msg)
        return data

    def get_init(self) -> dict[str, Any]:
        response = self._http.get("/api/common/init")
        response.raise_for_status()
        return response.json()

    def get_guardian_feed(
        self, kindergarten_id: int, child_id: int, date: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        response = self._http.get(
            f"/api/kindergartens/{kindergarten_id}/children/{child_id}/guardian-feed",
            params={"page": 1, "date": date},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", []), data.get("next_date")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
