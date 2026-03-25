# eliis-downloader

Download child photos and diary entries from [eliis.eu](https://eliis.eu) kindergarten management system.

## Features

- Downloads photos organized by year-month: `2025-09/2025-09-15 photo.jpg`
- Saves diary text summaries alongside photos as `.txt` files
- Skips photos from days the child was absent (configurable)
- Incremental: skips already-downloaded files on re-runs
- Early-stop optimization: only checks recent 30 days on subsequent runs

## Installation

```bash
# Run directly from GitHub
uvx git+https://github.com/lnagel/eliis-downloader ~/Downloads/Eliis

# Or install locally
uv sync
uv run eliis-download ~/Downloads/Eliis
```

Requires Python 3.13+.

## Usage

```bash
eliis-download [OPTIONS] OUTPUT_DIR
```

### Options

| Option | Description |
|---|---|
| `--email TEXT` | Eliis account email (env: `ELIIS_EMAIL`) |
| `--password TEXT` | Eliis account password (env: `ELIIS_PASSWORD`) |
| `--include-absent` | Include photos from days child was absent |
| `--child TEXT` | Filter by child name (partial match) |
| `--dry-run` | Show what would be downloaded without downloading |
| `--full` | Fetch entire history (disable early-stop optimization) |

### Environment variables

Create a `.env` file in the working directory:

```
ELIIS_EMAIL=your@email.com
ELIIS_PASSWORD=yourpassword
```

## Output structure

```
photos/
  2025-09/
    2025-09-01.txt
    2025-09-01 0123456789abcdef0123456789abcdef.jpg
    2025-09-01 123456789abcdef0123456789abcdef0.jpg
  2025-10/
    2025-10-03.txt
    2025-10-03 23456789abcdef0123456789abcdef01.jpg
```

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff format .
uv run ruff check . --fix
uv run ty check
```
