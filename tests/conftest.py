from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of how pytest is invoked
sys.path.insert(0, str(Path(__file__).parent.parent))

from pathlib import Path

import pytest

from app.config import AppConfig


def make_config(
    tmp_path: Path,
    *,
    source_dirs: list[Path] | None = None,
    raw_archive: Path | None = None,
    piece2_queue: Path | None = None,
    raw_extensions: frozenset[str] | None = None,
    jpeg_extensions: frozenset[str] | None = None,
    dry_run: bool = True,
    workers: int = 1,
) -> AppConfig:
    source = source_dirs or [tmp_path / "photos"]
    archive = raw_archive or (tmp_path / "raw-archive")
    queue = piece2_queue or (tmp_path / "piece2-queue")

    for d in source:
        d.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)
    queue.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        source_dirs=source,
        raw_archive=archive,
        piece2_queue=queue,
        raw_extensions=raw_extensions or frozenset({"ARW", "NEF"}),
        jpeg_extensions=jpeg_extensions or frozenset({"JPG", "JPEG"}),
        dry_run=dry_run,
        workers=workers,
    )


def touch(path: Path, content: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content or b"placeholder")
    return path


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    return make_config(tmp_path)


@pytest.fixture
def cfg_live(tmp_path: Path) -> AppConfig:
    return make_config(tmp_path, dry_run=False)
