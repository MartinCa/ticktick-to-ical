# CLAUDE.md

Instructions for Claude Code when working in this repository.

## Project

Python tool that converts TickTick CSV exports to iCalendar (`.ics`) files.
Single script: `ticktick_to_ical.py`. Tests live in `tests/`.

## Setup

```bash
pip install -r requirements-dev.txt
```

## Commands

| Task | Command |
|---|---|
| Run tests | `python -m unittest discover -s tests -v` |
| Format code | `ruff format .` |
| Lint code | `ruff check .` |
| Fix lint issues | `ruff check --fix .` |
| Run the converter | `python ticktick_to_ical.py [input.csv] [-o output_dir]` |

## Code Style

- Formatter and linter: **ruff** (configured via `pyproject.toml` if present, otherwise defaults)
- Always run `ruff format .` and `ruff check .` before committing
- CI enforces formatting and linting on every push

## Testing

- Tests use the standard `unittest` module — no pytest
- Integration tests load `tests/fixtures/sample.csv`
- Add tests for any new functionality
