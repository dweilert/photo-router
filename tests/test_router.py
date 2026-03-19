"""Tests for app.router — manifest building and file routing execution."""

from __future__ import annotations

from pathlib import Path

from app.router import OpKind, build_manifest, execute, route
from app.scanner import scan
from conftest import touch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw(parent: Path, stem: str, ext: str = "ARW") -> Path:
    return touch(parent / f"{stem}.{ext}")


def _jpeg(parent: Path, stem: str, ext: str = "JPG") -> Path:
    return touch(parent / f"{stem}.{ext}")


def _make_pair(src: Path, stem: str) -> tuple[Path, Path]:
    return _raw(src, stem), _jpeg(src, stem)


# ---------------------------------------------------------------------------
# Manifest building (dry-run — no filesystem changes)
# ---------------------------------------------------------------------------


class TestManifestBuilding:
    def test_pair_generates_copy_delete_skip(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        raw_path, jpeg_path = _make_pair(src, "DSC_0001")
        scan_result = scan(cfg)

        manifest = build_manifest(scan_result, cfg)

        kinds = [op.kind for op in manifest.operations]
        assert OpKind.COPY_RAW_TO_ARCHIVE in kinds
        assert OpKind.DELETE_SOURCE_RAW in kinds
        assert OpKind.SKIP_JPEG in kinds

    def test_orphan_raw_generates_copy_to_queue(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _raw(src, "ONLY_RAW")
        scan_result = scan(cfg)

        manifest = build_manifest(scan_result, cfg)

        kinds = [op.kind for op in manifest.operations]
        assert OpKind.COPY_RAW_TO_QUEUE in kinds
        assert OpKind.DELETE_SOURCE_RAW in kinds
        assert OpKind.COPY_RAW_TO_ARCHIVE not in kinds

    def test_orphan_jpeg_generates_no_operations(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _jpeg(src, "ONLY_JPEG")
        scan_result = scan(cfg)

        manifest = build_manifest(scan_result, cfg)

        assert len(manifest.operations) == 0

    def test_archive_path_mirrors_source_structure(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        sub = src / "2023" / "Hawaii"
        _raw(sub, "DSC_0001")
        _jpeg(sub, "DSC_0001")
        scan_result = scan(cfg)

        manifest = build_manifest(scan_result, cfg)

        copy_op = next(op for op in manifest.operations if op.kind == OpKind.COPY_RAW_TO_ARCHIVE)
        expected = cfg.raw_archive / "2023" / "Hawaii" / "DSC_0001.ARW"
        assert copy_op.destination == expected

    def test_queue_path_mirrors_source_structure(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        sub = src / "2023" / "Events"
        _raw(sub, "IMG_0001")
        scan_result = scan(cfg)

        manifest = build_manifest(scan_result, cfg)

        copy_op = next(op for op in manifest.operations if op.kind == OpKind.COPY_RAW_TO_QUEUE)
        expected = cfg.piece2_queue / "2023" / "Events" / "IMG_0001.ARW"
        assert copy_op.destination == expected

    def test_dry_run_flag_preserved(self, tmp_path, cfg):
        scan_result = scan(cfg)
        manifest = build_manifest(scan_result, cfg)
        assert manifest.dry_run is True

    def test_manifest_summaries(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _make_pair(src, "PAIRED")
        _raw(src, "ORPHAN_RAW")
        _jpeg(src, "ORPHAN_JPEG")
        scan_result = scan(cfg)

        manifest = build_manifest(scan_result, cfg)

        assert len(manifest.copies_to_archive) == 1
        assert len(manifest.copies_to_queue) == 1
        assert len(manifest.skipped_jpegs) == 1
        # Two deletes: one for the pair's RAW, one for the orphan RAW
        assert len(manifest.deletes) == 2


# ---------------------------------------------------------------------------
# Dry-run execution (must not touch filesystem)
# ---------------------------------------------------------------------------


class TestDryRunExecution:
    def test_dry_run_leaves_files_untouched(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        raw_path, jpeg_path = _make_pair(src, "DSC_0001")
        scan_result = scan(cfg)
        manifest = build_manifest(scan_result, cfg)

        execute(manifest)

        assert raw_path.exists(), "RAW should not be deleted in dry-run"
        assert jpeg_path.exists(), "JPEG should not be moved in dry-run"
        assert not (cfg.raw_archive / "DSC_0001.ARW").exists()

    def test_dry_run_operations_remain_pending(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _make_pair(src, "DSC_0001")
        scan_result = scan(cfg)
        manifest = build_manifest(scan_result, cfg)

        execute(manifest)

        non_skip_ops = [op for op in manifest.operations if op.kind != OpKind.SKIP_JPEG]
        assert all(op.pending for op in non_skip_ops)


# ---------------------------------------------------------------------------
# Live execution
# ---------------------------------------------------------------------------


class TestLiveExecution:
    def test_paired_raw_copied_to_archive(self, tmp_path, cfg_live):
        src = cfg_live.source_dirs[0]
        raw_path, jpeg_path = _make_pair(src, "DSC_0001")
        scan_result = scan(cfg_live)

        route(scan_result, cfg_live)

        dest = cfg_live.raw_archive / "DSC_0001.ARW"
        assert dest.exists(), "RAW should be in archive"

    def test_paired_raw_deleted_from_source(self, tmp_path, cfg_live):
        src = cfg_live.source_dirs[0]
        raw_path, _ = _make_pair(src, "DSC_0001")
        scan_result = scan(cfg_live)

        route(scan_result, cfg_live)

        assert not raw_path.exists(), "Source RAW should be deleted after copy"

    def test_paired_jpeg_left_in_place(self, tmp_path, cfg_live):
        src = cfg_live.source_dirs[0]
        _, jpeg_path = _make_pair(src, "DSC_0001")
        scan_result = scan(cfg_live)

        route(scan_result, cfg_live)

        assert jpeg_path.exists(), "JPEG must remain for immich"

    def test_orphan_raw_copied_to_queue(self, tmp_path, cfg_live):
        src = cfg_live.source_dirs[0]
        _raw(src, "ORPHAN")
        scan_result = scan(cfg_live)

        route(scan_result, cfg_live)

        dest = cfg_live.piece2_queue / "ORPHAN.ARW"
        assert dest.exists()

    def test_orphan_raw_deleted_from_source(self, tmp_path, cfg_live):
        src = cfg_live.source_dirs[0]
        raw_path = _raw(src, "ORPHAN")
        scan_result = scan(cfg_live)

        route(scan_result, cfg_live)

        assert not raw_path.exists()

    def test_orphan_jpeg_untouched(self, tmp_path, cfg_live):
        src = cfg_live.source_dirs[0]
        jpeg_path = _jpeg(src, "PHONE_SHOT")
        scan_result = scan(cfg_live)

        route(scan_result, cfg_live)

        assert jpeg_path.exists()

    def test_archive_directory_created_if_missing(self, tmp_path, cfg_live):
        src = cfg_live.source_dirs[0]
        sub = src / "deep" / "nested" / "dir"
        _raw(sub, "DSC_0001")
        _jpeg(sub, "DSC_0001")
        scan_result = scan(cfg_live)

        route(scan_result, cfg_live)

        dest = cfg_live.raw_archive / "deep" / "nested" / "dir" / "DSC_0001.ARW"
        assert dest.exists()

    def test_delete_skipped_if_copy_fails(self, tmp_path, cfg_live, monkeypatch):
        """Source RAW must NOT be deleted if the copy operation fails."""
        src = cfg_live.source_dirs[0]
        raw_path, _ = _make_pair(src, "DSC_0001")
        scan_result = scan(cfg_live)
        manifest = build_manifest(scan_result, cfg_live)

        import shutil

        def _fail_copy(src, dst):
            raise OSError("Simulated disk full")

        monkeypatch.setattr(shutil, "copy2", _fail_copy)
        execute(manifest, workers=1)

        assert raw_path.exists(), "Source RAW must survive a failed copy"
        failed = manifest.failed
        assert len(failed) > 0

    def test_all_operations_marked_successful(self, tmp_path, cfg_live):
        src = cfg_live.source_dirs[0]
        _make_pair(src, "DSC_0001")
        _make_pair(src, "DSC_0002")
        _raw(src, "ORPHAN")
        scan_result = scan(cfg_live)

        manifest = route(scan_result, cfg_live)

        assert len(manifest.failed) == 0
        assert all(op.success is True for op in manifest.operations)


# ---------------------------------------------------------------------------
# route() convenience function
# ---------------------------------------------------------------------------


class TestRouteConvenienceFunction:
    def test_route_dry_run_returns_manifest(self, tmp_path, cfg):
        src = cfg.source_dirs[0]
        _make_pair(src, "DSC_0001")
        scan_result = scan(cfg)

        manifest = route(scan_result, cfg)

        assert manifest.dry_run is True
        assert len(manifest.copies_to_archive) == 1
