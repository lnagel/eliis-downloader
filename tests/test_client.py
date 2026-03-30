from http.cookiejar import MozillaCookieJar

import httpx
import pytest
import respx

from eliis_downloader.client import BASE_URL, EliisAuthError, EliisClient, retry


@respx.mock
def test_login_success(tmp_path):
    respx.post(f"{BASE_URL}/api/auth/login").mock(
        return_value=httpx.Response(200, json={"user": {"id": 1, "fname": "Test"}})
    )
    with EliisClient(cookie_path=tmp_path / ".cookies") as client:
        result = client.login("test@example.com", "password123")
    assert result["user"]["id"] == 1


@respx.mock
def test_login_failure_status():
    respx.post(f"{BASE_URL}/api/auth/login").mock(return_value=httpx.Response(401, text="Unauthorized"))
    with EliisClient() as client, pytest.raises(EliisAuthError, match="Login failed"):
        client.login("bad@example.com", "wrong")


@respx.mock
def test_login_2fa_required():
    respx.post(f"{BASE_URL}/api/auth/login").mock(return_value=httpx.Response(200, json={"type": "2fa"}))
    with EliisClient() as client, pytest.raises(EliisAuthError, match="additional step"):
        client.login("test@example.com", "password123")


@respx.mock
def test_get_init():
    respx.get(f"{BASE_URL}/api/common/init").mock(
        return_value=httpx.Response(
            200,
            json={
                "kindergartens": [{"id": 1, "name": "Test KG"}],
                "children": [{"id": 10, "fname": "Child", "lname": "One", "kindergarten_id": 1}],
            },
        )
    )
    with EliisClient() as client:
        data = client.get_init()
    assert len(data["kindergartens"]) == 1
    assert data["children"][0]["fname"] == "Child"


@respx.mock
def test_get_guardian_feed():
    respx.get(f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "date": "2026-03-25",
                        "diaries": [
                            {
                                "course": "Group A",
                                "status": {"type": 1, "name": "Present"},
                                "texts": [
                                    {
                                        "summaries": [{"comment": "<p>Fun day</p>"}],
                                        "images": [
                                            {
                                                "id": 1,
                                                "filename": "abc.jpg",
                                                "url": "https://cdn.example.com/abc.jpg",
                                                "uploaded_at": "2026-03-25 10:00:00",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "next_date": "2026-03-20",
            },
        )
    )
    with EliisClient() as client:
        entries, next_date = client.get_guardian_feed(1, 10, "2026-03-25")
    assert len(entries) == 1
    assert next_date == "2026-03-20"
    assert entries[0]["date"] == "2026-03-25"


@respx.mock
def test_get_guardian_feed_end_of_data():
    respx.get(f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed").mock(
        return_value=httpx.Response(200, json={"data": [], "next_date": None})
    )
    with EliisClient() as client:
        entries, next_date = client.get_guardian_feed(1, 10, "2021-01-01")
    assert entries == []
    assert next_date is None


@respx.mock
def test_client_sends_required_headers():
    route = respx.get(f"{BASE_URL}/api/common/init").mock(return_value=httpx.Response(200, json={}))
    with EliisClient() as client:
        client.get_init()
    request = route.calls[0].request
    assert request.headers["X-Requested-With"] == "XMLHttpRequest"
    assert request.headers["Origin"] == "https://eliis.eu"


def test_retry_succeeds_after_failures(monkeypatch):
    monkeypatch.setattr("eliis_downloader.client.INITIAL_BACKOFF", 0.0)
    call_count = 0

    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TransportError("connection reset")
        return "ok"

    assert retry(flaky) == "ok"
    assert call_count == 3


def test_retry_raises_after_max_attempts(monkeypatch):
    monkeypatch.setattr("eliis_downloader.client.INITIAL_BACKOFF", 0.0)

    def always_fails():
        raise httpx.TransportError("connection reset")

    with pytest.raises(httpx.TransportError, match="connection reset"):
        retry(always_fails)


def test_retry_does_not_retry_client_errors():
    def client_error():
        raise httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(404),
        )

    with pytest.raises(httpx.HTTPStatusError):
        retry(client_error)


@respx.mock
def test_get_init_retries_on_server_error(monkeypatch):
    monkeypatch.setattr("eliis_downloader.client.INITIAL_BACKOFF", 0.0)
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(200, json={"kindergartens": [], "children": []})

    respx.get(f"{BASE_URL}/api/common/init").mock(side_effect=side_effect)
    with EliisClient() as client:
        data = client.get_init()
    assert data == {"kindergartens": [], "children": []}
    assert call_count == 2


@respx.mock
def test_login_saves_cookies(tmp_path):
    cookie_path = tmp_path / ".cookies"
    respx.post(f"{BASE_URL}/api/auth/login").mock(
        return_value=httpx.Response(
            200,
            json={"user": {"id": 1}},
            headers={"set-cookie": "eliis_csrf=jwt_token; Path=/; Domain=api.eliis.eu"},
        )
    )
    with EliisClient(cookie_path=cookie_path) as client:
        client.login("test@example.com", "pass")
    assert cookie_path.exists()
    jar = MozillaCookieJar()
    jar.load(str(cookie_path), ignore_discard=True, ignore_expires=True)
    assert any(c.name == "eliis_csrf" for c in jar)


@respx.mock
def test_has_session_with_valid_cookie(tmp_path):
    cookie_path = tmp_path / ".cookies"

    # First: login to save cookie
    respx.post(f"{BASE_URL}/api/auth/login").mock(
        return_value=httpx.Response(
            200,
            json={"user": {"id": 1}},
            headers={"set-cookie": "eliis_csrf=jwt_token; Path=/; Domain=api.eliis.eu"},
        )
    )
    respx.get(f"{BASE_URL}/api/common/init").mock(
        return_value=httpx.Response(200, json={"kindergartens": [], "children": []})
    )

    with EliisClient(cookie_path=cookie_path) as client:
        client.login("test@example.com", "pass")

    # Second: new client loads cookie and has_session succeeds
    with EliisClient(cookie_path=cookie_path) as client:
        assert client.has_session()


@respx.mock
def test_has_session_with_expired_cookie(tmp_path):
    cookie_path = tmp_path / ".cookies"

    # First: login to save cookie
    respx.post(f"{BASE_URL}/api/auth/login").mock(
        return_value=httpx.Response(
            200,
            json={"user": {"id": 1}},
            headers={"set-cookie": "eliis_csrf=jwt_token; Path=/; Domain=api.eliis.eu"},
        )
    )
    with EliisClient(cookie_path=cookie_path) as client:
        client.login("test@example.com", "pass")

    # Second: init returns 401 → session invalid
    respx.get(f"{BASE_URL}/api/common/init").mock(return_value=httpx.Response(401))
    with EliisClient(cookie_path=cookie_path) as client:
        assert not client.has_session()
    assert not cookie_path.exists()


def test_has_session_no_cookie_file(tmp_path):
    cookie_path = tmp_path / ".cookies"
    with EliisClient(cookie_path=cookie_path) as client:
        assert not client.has_session()
