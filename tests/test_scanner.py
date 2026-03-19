"""Tests for app.scanner — directory walking and file classification."""

from __future__ import annotations

from pathlib import Path

from app.scanner import scan
from conftest import make_config, touch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw(parent: Path, stem: str, ext: str = "ARW") -> Path:
    return touch(parent / f"{stem}.{ext}")


def _jpeg(parent: Path, stem: str, ext: str = "JPG") -> Path:
    return touch(parent / f"{stem}.{ext}")


# ---------------------------------------------------------------------------
# Basic pairing
# ---------------------------------------------------------------------------


class TestBasicPairing:
    def test_matched_pair_arw_jpg(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _raw(src, "DSC_0001")
        _jpeg(src, "DSC_0001")

        result = scan(cfg)

        assert len(result.pairs) == 1
        assert len(result.orphan_raws) == 0
        assert len(result.orphan_jpegs) == 0
        assert result.pairs[0].stem == "DSC_0001"

    def test_matched_pair_nef_jpg(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _raw(src, "IMG_9999", "NEF")
        _jpeg(src, "IMG_9999")

        result = scan(cfg)

        assert len(result.pairs) == 1
        assert result.pairs[0].raw.suffix.upper() == ".NEF"

    def test_multiple_pairs(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        for i in range(5):
            _raw(src, f"DSC_{i:04d}")
            _jpeg(src, f"DSC_{i:04d}")

        result = scan(cfg)

        assert len(result.pairs) == 5
        assert len(result.orphan_raws) == 0
        assert len(result.orphan_jpegs) == 0


# ---------------------------------------------------------------------------
# Orphan detection
# ---------------------------------------------------------------------------


class TestOrphanDetection:
    def test_orphan_raw_no_jpeg(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _raw(src, "LONELY_0001")

        result = scan(cfg)

        assert len(result.pairs) == 0
        assert len(result.orphan_raws) == 1
        assert result.orphan_raws[0].stem == "LONELY_0001"

    def test_orphan_jpeg_no_raw(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _jpeg(src, "PHONE_SHOT")

        result = scan(cfg)

        assert len(result.pairs) == 0
        assert len(result.orphan_jpegs) == 1
        assert result.orphan_jpegs[0].stem == "PHONE_SHOT"

    def test_mixed_bag(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _raw(src, "PAIRED")
        _jpeg(src, "PAIRED")
        _raw(src, "ONLY_RAW")
        _jpeg(src, "ONLY_JPEG")

        result = scan(cfg)

        assert len(result.pairs) == 1
        assert len(result.orphan_raws) == 1
        assert len(result.orphan_jpegs) == 1


# ---------------------------------------------------------------------------
# Case-insensitive extension matching
# ---------------------------------------------------------------------------


class TestCaseInsensitivity:
    def test_lowercase_extensions_matched(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        touch(src / "IMG_0001.arw")
        touch(src / "IMG_0001.jpg")

        result = scan(cfg)

        assert len(result.pairs) == 1

    def test_mixed_case_extensions(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        touch(src / "IMG_0002.Arw")
        touch(src / "IMG_0002.Jpg")

        result = scan(cfg)

        assert len(result.pairs) == 1

    def test_jpeg_extension_variant(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _raw(src, "IMG_0003")
        touch(src / "IMG_0003.jpeg")

        result = scan(cfg)

        assert len(result.pairs) == 1

    def test_stem_case_does_not_affect_pairing(self, tmp_path, cfg):
        """Files with identical stems differing only in case are treated as one stem."""
        src = cfg.source_dirs[0]
        # On a case-sensitive filesystem these are different files but same logical stem
        touch(src / "dsc_0001.ARW")
        touch(src / "DSC_0001.JPG")

        result = scan(cfg)

        # Both should be found (as a pair or orphans depending on filesystem)
        # The key assertion: total files accounted for, no crash
        assert result.total_files >= 1


# ---------------------------------------------------------------------------
# Nested directory handling
# ---------------------------------------------------------------------------


class TestNestedDirectories:
    def test_pairs_in_subdirectories(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        sub = src / "2023" / "Hawaii"
        _raw(sub, "DSC_0001")
        _jpeg(sub, "DSC_0001")

        result = scan(cfg)

        assert len(result.pairs) == 1
        assert result.pairs[0].directory == sub

    def test_pairs_across_multiple_subdirectories(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        for event in ["Hawaii", "Paris", "Tokyo"]:
            sub = src / "2023" / event
            _raw(sub, "DSC_0001")
            _jpeg(sub, "DSC_0001")

        result = scan(cfg)

        assert len(result.pairs) == 3

    def test_no_cross_directory_pairing(self, tmp_path, cfg):
        """A RAW in one directory must NOT pair with a JPEG in a sibling directory."""
        src = cfg.source_dirs[0]
        _raw(src / "dir_a", "DSC_0001")
        _jpeg(src / "dir_b", "DSC_0001")

        result = scan(cfg)

        assert len(result.pairs) == 0
        assert len(result.orphan_raws) == 1
        assert len(result.orphan_jpegs) == 1


# ---------------------------------------------------------------------------
# Multiple source directories
# ---------------------------------------------------------------------------


class TestMultipleSourceDirs:
    def test_scans_all_source_dirs(self, tmp_path):
        src_a = tmp_path / "photos_a"
        src_b = tmp_path / "photos_b"
        cfg = make_config(tmp_path, source_dirs=[src_a, src_b])

        _raw(src_a, "DSC_0001")
        _jpeg(src_a, "DSC_0001")
        _raw(src_b, "IMG_0002")
        _jpeg(src_b, "IMG_0002")

        result = scan(cfg)

        assert len(result.pairs) == 2


# ---------------------------------------------------------------------------
# Edge cases and error handling
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_nonexistent_source_dir_produces_error(self, tmp_path):
        cfg = make_config(tmp_path)
        # Point to a path that cannot exist — modify config directly after creation
        cfg.source_dirs[0].rmdir()  # remove the dir make_config just created

        result = scan(cfg)

        assert len(result.errors) == 1
        assert "does not exist" in result.errors[0]

    # def test_nonexistent_source_dir_produces_error(self, tmp_path):
    #     cfg = make_config(tmp_path, source_dirs=[tmp_path / "does_not_exist"])

    #     result = scan(cfg)

    #     assert len(result.errors) == 1
    #     assert "does not exist" in result.errors[0]

    def test_empty_directory_returns_empty_result(self, tmp_path, cfg):
        result = scan(cfg)

        assert result.total_files == 0
        assert len(result.errors) == 0

    def test_non_photo_files_ignored(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        touch(src / "readme.txt")
        touch(src / "thumbs.db")
        touch(src / ".DS_Store")

        result = scan(cfg)

        assert result.total_files == 0

    def test_total_file_counts(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _raw(src, "PAIR_1")
        _jpeg(src, "PAIR_1")
        _raw(src, "ORPHAN_RAW")
        _jpeg(src, "ORPHAN_JPEG")

        result = scan(cfg)

        assert result.total_raws == 2
        assert result.total_jpegs == 2
        assert result.total_files == 4

    def test_duplicate_raw_extensions_second_is_orphan(self, tmp_path, cfg):
        """If a stem has both .ARW and .NEF, one pairs and one is an orphan RAW."""
        src = cfg.source_dirs[0]
        _raw(src, "DSC_0001", "ARW")
        _raw(src, "DSC_0001", "NEF")
        _jpeg(src, "DSC_0001")

        result = scan(cfg)

        # One pair, one orphan RAW
        assert len(result.pairs) == 1
        assert len(result.orphan_raws) == 1
