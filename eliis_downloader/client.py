import time
from collections.abc import Callable
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Self

import httpx

MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0

BASE_URL = "https://api.eliis.eu"
COMMON_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://eliis.eu",
    "Referer": "https://eliis.eu/",
    "Accept": "application/json",
}

DEFAULT_COOKIE_PATH = Path(".eliis_cookies.txt")


class EliisAuthError(Exception):
    pass


def retry[T](fn: Callable[[], T]) -> T:
    """Retry a function up to MAX_RETRIES times with exponential backoff."""
    last_exception: Exception = RuntimeError("unreachable")
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except (httpx.HTTPStatusError, httpx.TransportError) as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:  # noqa: PLR2004
                raise
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                delay = INITIAL_BACKOFF * (2**attempt)
                time.sleep(delay)
    raise last_exception


class EliisClient:
    def __init__(self, cookie_path: Path = DEFAULT_COOKIE_PATH) -> None:
        self._cookie_path = cookie_path
        self._jar = MozillaCookieJar()
        if cookie_path.exists():
            self._jar.load(str(cookie_path), ignore_discard=True, ignore_expires=True)
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers=COMMON_HEADERS,
            cookies=self._jar,
            follow_redirects=True,
            timeout=30.0,
        )

    def _save_cookies(self) -> None:
        """Persist current cookies to disk."""
        self._jar.save(str(self._cookie_path), ignore_discard=True, ignore_expires=True)

    def login(self, email: str, password: str) -> dict[str, Any]:
        response = self._http.post("/api/auth/login", json={"username": email, "password": password, "platform": "web"})
        if response.status_code != 200:  # noqa: PLR2004
            msg = f"Login failed: {response.status_code} {response.text}"
            raise EliisAuthError(msg)
        data = response.json()
        if isinstance(data, dict) and data.get("type"):
            msg = f"Login requires additional step: {data.get('type')}"
            raise EliisAuthError(msg)
        self._save_cookies()
        return data

    def has_session(self) -> bool:
        """Check whether a saved session cookie is still valid."""
        if not any(c.name == "eliis_csrf" for c in self._jar):
            return False
        try:
            self.get_init()
        except (httpx.HTTPStatusError, httpx.TransportError):
            self._clear_cookies()
            return False
        return True

    def _clear_cookies(self) -> None:
        self._jar.clear()
        if self._cookie_path.exists():
            self._cookie_path.unlink()

    def get_init(self) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            response = self._http.get("/api/common/init")
            response.raise_for_status()
            return response.json()

        return retry(_call)

    def get_guardian_feed(
        self, kindergarten_id: int, child_id: int, date: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        def _call() -> tuple[list[dict[str, Any]], str | None]:
            response = self._http.get(
                f"/api/kindergartens/{kindergarten_id}/children/{child_id}/guardian-feed",
                params={"page": 1, "date": date},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", []), data.get("next_date")

        return retry(_call)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
