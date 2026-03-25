from __future__ import annotations

import httpx
import pytest
import respx

from eliis_downloader.client import BASE_URL, EliisAuthError, EliisClient


@respx.mock
def test_login_success():
    respx.post(f"{BASE_URL}/api/auth/login").mock(
        return_value=httpx.Response(200, json={"user": {"id": 1, "fname": "Test"}})
    )
    with EliisClient() as client:
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
