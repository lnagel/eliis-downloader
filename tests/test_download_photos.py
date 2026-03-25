import httpx
import respx

from eliis_downloader.client import BASE_URL, EliisClient
from eliis_downloader.downloader import download_photos, run


def _feed_response(entries, next_date=None):
    return httpx.Response(200, json={"data": entries, "next_date": next_date})


def _make_feed_entry(date, status_type=1, images=None, comment="<p>Test</p>"):
    status = {"type": status_type, "name": "test"} if status_type is not None else None
    return {
        "date": date,
        "diaries": [
            {
                "course": "Group",
                "status": status,
                "texts": [
                    {
                        "summaries": [{"comment": comment}] if comment else [],
                        "images": images or [],
                    }
                ],
            }
        ],
    }


def _make_image(filename="abc.jpg", url="https://cdn.test/abc.jpg"):
    return {"id": 1, "filename": filename, "url": url, "uploaded_at": "2026-03-25 10:00:00"}


@respx.mock
def test_download_photos_dry_run(tmp_path):
    feed_url = f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed"
    img = _make_image()
    entry = _make_feed_entry("2026-03-25", images=[img])

    respx.get(feed_url).mock(
        side_effect=[
            _feed_response([entry], next_date=None),
        ]
    )

    with EliisClient() as client:
        stats = download_photos(client, 1, 10, "Test Child", tmp_path, include_absent=False, dry_run=True, full=False)

    assert stats.downloaded == 1
    assert stats.skipped == 0
    assert stats.absent_skipped == 0
    assert not (tmp_path / "2026-03" / "2026-03-25 abc.jpg").exists()


@respx.mock
def test_download_photos_actual_download(tmp_path):
    feed_url = f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed"
    img = _make_image(url="https://cdn.test/photo.jpg")
    entry = _make_feed_entry("2026-03-25", images=[img])

    respx.get(feed_url).mock(return_value=_feed_response([entry], next_date=None))
    respx.get("https://cdn.test/photo.jpg").mock(return_value=httpx.Response(200, content=b"JPEG_DATA"))

    with EliisClient() as client:
        stats = download_photos(client, 1, 10, "Test Child", tmp_path, include_absent=False, dry_run=False, full=False)

    assert stats.downloaded == 1
    assert stats.skipped == 0
    target = tmp_path / "2026-03" / "2026-03-25 abc.jpg"
    assert target.exists()
    assert target.read_bytes() == b"JPEG_DATA"
    # Text file should also be created
    text_path = tmp_path / "2026-03" / "2026-03-25.txt"
    assert text_path.exists()
    assert "Test" in text_path.read_text()


@respx.mock
def test_download_photos_skip_existing(tmp_path):
    feed_url = f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed"
    img = _make_image()
    entry = _make_feed_entry("2026-03-25", images=[img])

    respx.get(feed_url).mock(return_value=_feed_response([entry], next_date=None))

    # Pre-create the file
    month_dir = tmp_path / "2026-03"
    month_dir.mkdir(parents=True)
    (month_dir / "2026-03-25 abc.jpg").write_bytes(b"existing")

    with EliisClient() as client:
        stats = download_photos(client, 1, 10, "Test Child", tmp_path, include_absent=False, dry_run=False, full=False)

    assert stats.downloaded == 0
    assert stats.skipped == 1


@respx.mock
def test_download_photos_absent_skipped(tmp_path):
    feed_url = f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed"
    img = _make_image()
    entry = _make_feed_entry("2026-03-25", status_type=0, images=[img])

    respx.get(feed_url).mock(return_value=_feed_response([entry], next_date=None))

    with EliisClient() as client:
        stats = download_photos(client, 1, 10, "Test Child", tmp_path, include_absent=False, dry_run=True, full=False)

    assert stats.downloaded == 0
    assert stats.absent_skipped == 1


@respx.mock
def test_download_photos_include_absent(tmp_path):
    feed_url = f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed"
    img = _make_image(url="https://cdn.test/photo.jpg")
    entry = _make_feed_entry("2026-03-25", status_type=0, images=[img])

    respx.get(feed_url).mock(return_value=_feed_response([entry], next_date=None))
    respx.get("https://cdn.test/photo.jpg").mock(return_value=httpx.Response(200, content=b"IMG"))

    with EliisClient() as client:
        stats = download_photos(client, 1, 10, "Test Child", tmp_path, include_absent=True, dry_run=False, full=False)

    assert stats.downloaded == 1


@respx.mock
def test_download_photos_pagination_stops_when_all_exist(tmp_path):
    feed_url = f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed"
    img = _make_image()
    recent_entry = _make_feed_entry("2026-03-25", images=[img])
    old_entry = _make_feed_entry("2026-01-15", images=[_make_image("old.jpg", "https://cdn.test/old.jpg")])

    # Pre-create old image
    month_dir = tmp_path / "2026-01"
    month_dir.mkdir(parents=True)
    (month_dir / "2026-01-15 old.jpg").write_bytes(b"exists")

    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _feed_response([recent_entry], next_date="2026-01-15")
        return _feed_response([old_entry], next_date="2025-12-01")

    respx.get(feed_url).mock(side_effect=side_effect)
    respx.get("https://cdn.test/abc.jpg").mock(return_value=httpx.Response(200, content=b"IMG"))

    with EliisClient() as client:
        stats = download_photos(client, 1, 10, "Test Child", tmp_path, include_absent=False, dry_run=False, full=False)

    assert stats.downloaded == 1  # only the recent one
    assert stats.skipped == 1  # old one exists
    assert call_count == 2  # stopped after finding all-existing page


@respx.mock
def test_download_photos_text_only_day(tmp_path):
    feed_url = f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed"
    entry = _make_feed_entry("2026-03-25", comment="<p>Just text today</p>")

    respx.get(feed_url).mock(return_value=_feed_response([entry], next_date=None))

    with EliisClient() as client:
        stats = download_photos(client, 1, 10, "Test Child", tmp_path, include_absent=False, dry_run=False, full=False)

    assert stats.downloaded == 0
    text_path = tmp_path / "2026-03" / "2026-03-25.txt"
    assert text_path.exists()
    assert "Just text today" in text_path.read_text()


@respx.mock
def test_download_photos_dry_run_text(tmp_path):
    feed_url = f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed"
    entry = _make_feed_entry("2026-03-25", comment="<p>Text</p>")

    respx.get(feed_url).mock(return_value=_feed_response([entry], next_date=None))

    with EliisClient() as client:
        download_photos(client, 1, 10, "Test Child", tmp_path, include_absent=False, dry_run=True, full=False)

    assert not (tmp_path / "2026-03" / "2026-03-25.txt").exists()


@respx.mock
def test_run_full_flow(tmp_path):
    respx.post(f"{BASE_URL}/api/auth/login").mock(return_value=httpx.Response(200, json={"user": {"id": 1}}))
    respx.get(f"{BASE_URL}/api/common/init").mock(
        return_value=httpx.Response(
            200,
            json={
                "kindergartens": [{"id": 1, "name": "KG"}],
                "children": [{"id": 10, "fname": "Test", "lname": "Child", "kindergarten_id": 1}],
            },
        )
    )
    respx.get(f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed").mock(
        return_value=_feed_response([], next_date=None)
    )

    run(tmp_path, "test@example.com", "pass", include_absent=False, child_filter=None, dry_run=True, full=False)


@respx.mock
def test_run_no_children(tmp_path):
    respx.post(f"{BASE_URL}/api/auth/login").mock(return_value=httpx.Response(200, json={"user": {"id": 1}}))
    respx.get(f"{BASE_URL}/api/common/init").mock(
        return_value=httpx.Response(200, json={"kindergartens": [], "children": []})
    )

    run(tmp_path, "test@example.com", "pass", include_absent=False, child_filter=None, dry_run=True, full=False)


@respx.mock
def test_run_child_filter(tmp_path):
    respx.post(f"{BASE_URL}/api/auth/login").mock(return_value=httpx.Response(200, json={"user": {"id": 1}}))
    respx.get(f"{BASE_URL}/api/common/init").mock(
        return_value=httpx.Response(
            200,
            json={
                "kindergartens": [{"id": 1, "name": "KG"}],
                "children": [
                    {"id": 10, "fname": "Alice", "lname": "One", "kindergarten_id": 1},
                    {"id": 11, "fname": "Bob", "lname": "Two", "kindergarten_id": 1},
                ],
            },
        )
    )
    # Only Alice should be fetched
    respx.get(f"{BASE_URL}/api/kindergartens/1/children/10/guardian-feed").mock(
        return_value=_feed_response([], next_date=None)
    )

    run(tmp_path, "test@example.com", "pass", include_absent=False, child_filter="Alice", dry_run=True, full=False)
