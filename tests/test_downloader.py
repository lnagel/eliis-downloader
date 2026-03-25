from __future__ import annotations

from pathlib import Path

from eliis_downloader.downloader import build_diary_text, collect_images, strip_html


def test_strip_html_basic():
    assert strip_html("<p>Hello world</p>") == "Hello world"


def test_strip_html_with_lists():
    html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
    result = strip_html(html)
    assert "Item 1" in result
    assert "Item 2" in result


def test_strip_html_with_entities():
    assert strip_html("<p>&amp; &lt; &gt;</p>") == "& < >"


def test_strip_html_br_tags():
    assert strip_html("line1<br/>line2") == "line1\nline2"


def test_build_diary_text():
    diaries = [
        {
            "course": "Group A",
            "texts": [
                {"summaries": [{"comment": "<p>Drawing today.</p>"}, {"comment": "<p>Music class.</p>"}], "images": []}
            ],
        }
    ]
    text = build_diary_text(diaries)
    assert "Group A" in text
    assert "Drawing today." in text
    assert "Music class." in text


def test_build_diary_text_empty():
    assert build_diary_text([]) == ""
    assert build_diary_text([{"course": "A", "texts": [{"summaries": [], "images": []}]}]) == ""


def _make_entry(date: str, status_type: int | None, *, images: list | None = None, comment: str = "") -> dict:
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


def _make_image(filename: str = "abc.jpg", url: str = "https://cdn/abc.jpg") -> dict:
    return {"id": 1, "filename": filename, "url": url, "uploaded_at": "2026-03-25 10:00:00"}


def test_collect_images_present_day():
    entries = [_make_entry("2026-03-25", 1, images=[_make_image()])]
    result = collect_images(entries, include_absent=False)
    assert len(result) == 1
    assert result[0][0] == "2026-03-25"
    assert result[0][1] == "abc.jpg"


def test_collect_images_absent_day_skipped():
    entries = [_make_entry("2026-03-25", 0, images=[_make_image()])]
    result = collect_images(entries, include_absent=False)
    assert len(result) == 0


def test_collect_images_absent_day_included():
    entries = [_make_entry("2026-03-25", 0, images=[_make_image()])]
    result = collect_images(entries, include_absent=True)
    assert len(result) == 1


def test_collect_images_null_status_included():
    entries = [_make_entry("2026-03-25", None, images=[_make_image()])]
    result = collect_images(entries, include_absent=False)
    assert len(result) == 1


def test_collect_images_text_only_entry():
    entries = [_make_entry("2026-03-25", 1, comment="<p>Fun day</p>")]
    result = collect_images(entries, include_absent=False)
    assert len(result) == 1
    assert result[0][1] == ""  # no filename
    assert "Fun day" in result[0][3]  # has diary text


def test_collect_images_with_diary_text():
    entries = [_make_entry("2026-03-25", 1, images=[_make_image()], comment="<p>Art class</p>")]
    result = collect_images(entries, include_absent=False)
    assert len(result) == 1
    assert "Art class" in result[0][3]


def test_file_path_construction(tmp_path: Path):
    date = "2025-09-15"
    filename = "abc123.jpg"
    month_dir = tmp_path / date[:7]
    target_path = month_dir / f"{date} {filename}"
    assert str(target_path).endswith("2025-09/2025-09-15 abc123.jpg")


def test_skip_existing_file(tmp_path: Path):
    date = "2025-09-15"
    filename = "abc123.jpg"
    month_dir = tmp_path / date[:7]
    month_dir.mkdir(parents=True)
    target_path = month_dir / f"{date} {filename}"
    target_path.write_bytes(b"fake image data")
    assert target_path.exists()
