"""Tests for app.config — loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppConfig, load_config


def test_load_config_valid(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
source_dirs:
  - /photos
raw_archive: /raw-archive
piece2_queue: /piece2-queue
raw_extensions: [ARW, NEF]
jpeg_extensions: [JPG, JPEG]
dry_run: true
workers: 4
""")
    cfg = load_config(cfg_file)
    assert cfg.dry_run is True
    assert cfg.workers == 4
    assert Path("/photos") in cfg.source_dirs
    assert cfg.raw_archive == Path("/raw-archive")


def test_load_config_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")


def test_load_config_no_source_dirs(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
source_dirs: []
raw_archive: /raw-archive
piece2_queue: /piece2-queue
""")
    with pytest.raises(ValueError, match="at least one source_dir"):
        load_config(cfg_file)


def test_is_raw(tmp_path):
    cfg = AppConfig(
        source_dirs=[tmp_path],
        raw_archive=tmp_path,
        piece2_queue=tmp_path,
        raw_extensions=frozenset({"ARW", "NEF"}),
        jpeg_extensions=frozenset({"JPG", "JPEG"}),
    )
    assert cfg.is_raw(Path("photo.ARW")) is True
    assert cfg.is_raw(Path("photo.arw")) is True
    assert cfg.is_raw(Path("photo.JPG")) is False


def test_is_jpeg(tmp_path):
    cfg = AppConfig(
        source_dirs=[tmp_path],
        raw_archive=tmp_path,
        piece2_queue=tmp_path,
        raw_extensions=frozenset({"ARW", "NEF"}),
        jpeg_extensions=frozenset({"JPG", "JPEG"}),
    )
    assert cfg.is_jpeg(Path("photo.JPG")) is True
    assert cfg.is_jpeg(Path("photo.jpeg")) is True
    assert cfg.is_jpeg(Path("photo.ARW")) is False
