"""Configuration loading and validation for photo-router."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class AppConfig:
    source_dirs: list[Path]
    raw_archive: Path
    piece2_queue: Path
    raw_extensions: frozenset[str]
    jpeg_extensions: frozenset[str]
    dry_run: bool = True
    workers: int = 4

    def is_raw(self, path: Path) -> bool:
        return path.suffix.lstrip(".").upper() in self.raw_extensions

    def is_jpeg(self, path: Path) -> bool:
        return path.suffix.lstrip(".").upper() in self.jpeg_extensions


def load_config(config_path: Path | str = "config.yaml") -> AppConfig:
    """Load and validate configuration from a YAML file."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open() as fh:
        raw = yaml.safe_load(fh)

    source_dirs = [Path(d) for d in raw.get("source_dirs", [])]
    if not source_dirs:
        raise ValueError("config.yaml must define at least one source_dir")

    raw_exts = frozenset(e.upper() for e in raw.get("raw_extensions", ["ARW", "NEF"]))
    jpeg_exts = frozenset(e.upper() for e in raw.get("jpeg_extensions", ["JPG", "JPEG"]))

    return AppConfig(
        source_dirs=source_dirs,
        raw_archive=Path(raw["raw_archive"]),
        piece2_queue=Path(raw["piece2_queue"]),
        raw_extensions=raw_exts,
        jpeg_extensions=jpeg_exts,
        dry_run=bool(raw.get("dry_run", True)),
        workers=int(raw.get("workers", 4)),
    )
