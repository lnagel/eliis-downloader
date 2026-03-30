import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

import httpx
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn

from eliis_downloader.client import DEFAULT_COOKIE_PATH, EliisClient, retry

PRESENT_STATUS_TYPE = 1
RECENT_DAYS = 30
TIMEZONE = ZoneInfo("Europe/Tallinn")

console = Console()


class FeedItem(NamedTuple):
    date: str
    filename: str
    url: str
    diary_text: str
    uploaded_at: str


def _parse_uploaded_at(uploaded_at: str) -> float | None:
    """Parse uploaded_at string (UTC) to a Unix timestamp."""
    if not uploaded_at:
        return None
    try:
        # Format: "2026-03-25 10:00:00.000" — truncate milliseconds for parsing
        dt = datetime.strptime(uploaded_at[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError:
        return None


def strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"</li>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    return text.strip()


def build_diary_text(diaries: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for diary in diaries:
        course = diary.get("course", "")
        texts = diary.get("texts", [])
        summaries_text: list[str] = []
        for text_entry in texts:
            for summary in text_entry.get("summaries", []):
                comment = summary.get("comment", "")
                if comment:
                    summaries_text.append(strip_html(comment))
        if summaries_text:
            parts.append(f"{course}\n{'=' * len(course)}\n" + "\n\n".join(summaries_text))
    return "\n\n".join(parts)


def collect_images(
    entries: list[dict[str, Any]],
    *,
    include_absent: bool,
) -> list[FeedItem]:
    """Extract FeedItem tuples from guardian-feed entries."""
    results: list[FeedItem] = []
    for entry in entries:
        date = entry["date"]
        diaries = entry.get("diaries", [])
        diary_text = build_diary_text(diaries)

        has_images = False
        for diary in diaries:
            status = diary.get("status")
            if not include_absent and status is not None and status.get("type") != PRESENT_STATUS_TYPE:
                continue

            for text_entry in diary.get("texts", []):
                for image in text_entry.get("images", []):
                    url = image.get("url")
                    filename = image.get("filename", "")
                    if url and filename:
                        uploaded_at = image.get("uploaded_at", "")
                        results.append(FeedItem(date, filename, url, diary_text, uploaded_at))
                        has_images = True

        if not has_images and diary_text:
            results.append(FeedItem(date, "", "", diary_text, ""))

    return results


def count_absent_images(entries: list[dict[str, Any]]) -> int:
    """Count images on absent days for reporting."""
    count = 0
    for entry in entries:
        for diary in entry.get("diaries", []):
            status = diary.get("status")
            if status is not None and status.get("type") != PRESENT_STATUS_TYPE:
                for text_entry in diary.get("texts", []):
                    count += len(text_entry.get("images", []))
    return count


@dataclass
class DownloadStats:
    downloaded: int = 0
    skipped: int = 0
    absent_skipped: int = 0


def _fetch_all_items(  # noqa: PLR0913
    client: EliisClient,
    kindergarten_id: int,
    child_id: int,
    output_dir: Path,
    *,
    include_absent: bool,
    full: bool,
) -> tuple[list[FeedItem], int]:
    """Paginate guardian-feed and collect all image items. Returns (items, absent_count)."""
    now = datetime.now(tz=TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    cutoff_date = (now - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%d")
    current_date: str | None = today
    all_items: list[FeedItem] = []
    absent_count = 0

    early_stopped = False
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        fetch_task = progress.add_task("Fetching feed...", total=None)

        while current_date is not None:
            entries, next_date = client.get_guardian_feed(kindergarten_id, child_id, current_date)
            progress.update(fetch_task, advance=len(entries))

            items = collect_images(entries, include_absent=include_absent)
            if not include_absent:
                absent_count += count_absent_images(entries)
            all_items.extend(items)

            if not full and next_date is not None and next_date < cutoff_date:
                page_images = [(item.date, item.filename) for item in items if item.filename]
                if page_images:
                    all_exist = all(
                        (output_dir / date[:7] / f"{date} {filename}").exists() for date, filename in page_images
                    )
                    if all_exist:
                        early_stopped = True
                        break

            current_date = next_date

        if early_stopped:
            progress.update(fetch_task, description="Fetching feed... done (reached already-downloaded content)")
        else:
            progress.update(fetch_task, description="Fetching feed... done")

    return all_items, absent_count


def _download_image(http: httpx.Client, url: str, target_path: Path, *, uploaded_at: str) -> None:
    """Download a single image from a URL to target_path, setting mtime to uploaded_at."""

    def _call() -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with http.stream("GET", url) as response:
            response.raise_for_status()
            with target_path.open("wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)

    retry(_call)

    timestamp = _parse_uploaded_at(uploaded_at)
    if timestamp is not None:
        os.utime(target_path, (timestamp, timestamp))


def _save_images(
    image_items: list[FeedItem],
    output_dir: Path,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    """Download images, skipping existing ones. Returns (downloaded, skipped)."""
    downloaded = 0
    skipped = 0

    with (
        httpx.Client(follow_redirects=True, timeout=60.0) as http,
        Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress,
    ):
        task = progress.add_task("Downloading...", total=len(image_items))

        for item in image_items:
            target_path = output_dir / item.date[:7] / f"{item.date} {item.filename}"

            if target_path.exists():
                skipped += 1
                timestamp = _parse_uploaded_at(item.uploaded_at)
                if timestamp is not None and target_path.stat().st_mtime != timestamp:
                    os.utime(target_path, (timestamp, timestamp))
            elif dry_run:
                console.print(f"  [dim]Would download:[/dim] {target_path}")
                downloaded += 1
            else:
                _download_image(http, item.url, target_path, uploaded_at=item.uploaded_at)
                downloaded += 1

            progress.update(task, advance=1)

    return downloaded, skipped


def _text_file_timestamp(date: str) -> float:
    """Return a Unix timestamp for 17:30 Estonian time on the given date."""
    dt = datetime.strptime(date, "%Y-%m-%d").replace(hour=17, minute=30, tzinfo=TIMEZONE)
    return dt.timestamp()


def _save_texts(text_items: dict[str, str], output_dir: Path, *, dry_run: bool) -> None:
    """Save diary text files, skipping writes when content is unchanged."""
    for date, text in text_items.items():
        month_dir = output_dir / date[:7]
        text_path = month_dir / f"{date}.txt"
        if dry_run:
            if not text_path.exists():
                console.print(f"  [dim]Would write:[/dim] {text_path}")
            continue
        timestamp = _text_file_timestamp(date)
        if text_path.exists() and text_path.read_text(encoding="utf-8") == text:
            if text_path.stat().st_mtime != timestamp:
                os.utime(text_path, (timestamp, timestamp))
            continue
        month_dir.mkdir(parents=True, exist_ok=True)
        text_path.write_text(text, encoding="utf-8")
        os.utime(text_path, (timestamp, timestamp))


def download_photos(  # noqa: PLR0913
    client: EliisClient,
    kindergarten_id: int,
    child_id: int,
    child_name: str,
    output_dir: Path,
    *,
    include_absent: bool,
    dry_run: bool,
    full: bool,
) -> DownloadStats:
    console.print(f"\n[bold]Fetching photos for {child_name}...[/bold]")

    all_items, absent_skipped = _fetch_all_items(
        client, kindergarten_id, child_id, output_dir, include_absent=include_absent, full=full
    )

    image_items = [item for item in all_items if item.filename]
    text_items: dict[str, str] = {}
    for item in all_items:
        if item.diary_text and item.date not in text_items:
            text_items[item.date] = item.diary_text

    downloaded, skipped = _save_images(image_items, output_dir, dry_run=dry_run)
    _save_texts(text_items, output_dir, dry_run=dry_run)

    return DownloadStats(downloaded=downloaded, skipped=skipped, absent_skipped=absent_skipped)


def run(  # noqa: PLR0913
    output_dir: Path,
    email: str,
    password: str,
    *,
    include_absent: bool,
    child_filter: str | None,
    dry_run: bool,
    full: bool,
    cookie_path: Path = DEFAULT_COOKIE_PATH,
) -> None:
    with EliisClient(cookie_path=cookie_path) as client:
        if client.has_session():
            console.print("[bold]Resuming saved session...[/bold]")
        else:
            console.print("[bold]Logging in to eliis.eu...[/bold]")
            client.login(email, password)

        init_data = client.get_init()
        children = init_data.get("children", [])
        kindergartens = {kg["id"]: kg["name"] for kg in init_data.get("kindergartens", [])}

        if not children:
            console.print("[red]No children found in your account.[/red]")
            return

        for child in children:
            name = f"{child['fname']} {child['lname']}"
            if child_filter and child_filter.lower() not in name.lower():
                continue

            kg_id = child["kindergarten_id"]
            kg_name = kindergartens.get(kg_id, f"Kindergarten {kg_id}")
            console.print(f"\n[bold blue]{name}[/bold blue] at [bold]{kg_name}[/bold]")

            stats = download_photos(
                client, kg_id, child["id"], name, output_dir, include_absent=include_absent, dry_run=dry_run, full=full
            )

            console.print(f"\n  [green]{stats.downloaded} downloaded[/green]", end="")
            console.print(f", [yellow]{stats.skipped} skipped[/yellow]", end="")
            if stats.absent_skipped:
                console.print(f", [dim]{stats.absent_skipped} absent-day skipped[/dim]", end="")
            console.print()
