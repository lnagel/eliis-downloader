from pathlib import Path

import click
from dotenv import load_dotenv

from eliis_downloader.client import EliisAuthError
from eliis_downloader.downloader import run

load_dotenv()


@click.command()
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.option("--email", envvar="ELIIS_EMAIL", prompt="Eliis email", help="Eliis account email (env: ELIIS_EMAIL)")
@click.option(
    "--password",
    envvar="ELIIS_PASSWORD",
    prompt="Eliis password",
    hide_input=True,
    help="Eliis account password (env: ELIIS_PASSWORD)",
)
@click.option("--include-absent", is_flag=True, default=False, help="Include photos from days child was absent")
@click.option("--child", "child_filter", default=None, help="Filter by child name (partial match)")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be downloaded without downloading")
@click.option("--full", is_flag=True, default=False, help="Fetch entire history (disable early-stop optimization)")
@click.option(
    "--cookies",
    "cookie_path",
    type=click.Path(path_type=Path),
    default=".eliis_cookies.txt",
    show_default=True,
    help="Path to session cookie file",
)
def main(  # noqa: PLR0913
    output_dir: Path,
    email: str,
    password: str,
    *,
    include_absent: bool,
    child_filter: str | None,
    dry_run: bool,
    full: bool,
    cookie_path: Path,
) -> None:
    """Download child photos from eliis.eu into OUTPUT_DIR, organized by year-month."""
    try:
        run(
            output_dir=output_dir,
            email=email,
            password=password,
            include_absent=include_absent,
            child_filter=child_filter,
            dry_run=dry_run,
            full=full,
            cookie_path=cookie_path,
        )
    except EliisAuthError as e:
        raise click.ClickException(str(e)) from None
