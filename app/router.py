"""Router — executes or simulates the file routing operations.

Takes a ScanResult and routes files according to the rules:

  Paired (RAW + JPEG):
    - Copy RAW  → raw_archive  (mirroring source directory structure)
    - JPEG      → stays in place (immich keeps seeing it)
    - Delete RAW from source after successful copy

  Orphan RAW (no JPEG):
    - Copy RAW  → piece2_queue (mirroring source directory structure)
    - Delete RAW from source after successful copy

  Orphan JPEG:
    - No action taken

When dry_run=True no files are touched; a manifest of intended operations
is returned instead so the caller can present a preview.
"""

from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from app.config import AppConfig
from app.scanner import ScanResult

# ---------------------------------------------------------------------------
# Operation model
# ---------------------------------------------------------------------------


class OpKind(Enum):
    COPY_RAW_TO_ARCHIVE = auto()
    COPY_RAW_TO_QUEUE = auto()
    DELETE_SOURCE_RAW = auto()
    SKIP_JPEG = auto()


@dataclass
class Operation:
    kind: OpKind
    source: Path
    destination: Path | None = None  # None for DELETE and SKIP
    success: bool | None = None  # None = not yet executed
    error: str | None = None

    @property
    def pending(self) -> bool:
        return self.success is None


@dataclass
class RoutingManifest:
    """Full record of what was (or would be) done."""

    operations: list[Operation] = field(default_factory=list)
    dry_run: bool = True

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def _ops_of_kind(self, kind: OpKind) -> list[Operation]:
        return [op for op in self.operations if op.kind == kind]

    @property
    def copies_to_archive(self) -> list[Operation]:
        return self._ops_of_kind(OpKind.COPY_RAW_TO_ARCHIVE)

    @property
    def copies_to_queue(self) -> list[Operation]:
        return self._ops_of_kind(OpKind.COPY_RAW_TO_QUEUE)

    @property
    def deletes(self) -> list[Operation]:
        return self._ops_of_kind(OpKind.DELETE_SOURCE_RAW)

    @property
    def skipped_jpegs(self) -> list[Operation]:
        return self._ops_of_kind(OpKind.SKIP_JPEG)

    @property
    def failed(self) -> list[Operation]:
        return [op for op in self.operations if op.success is False]

    @property
    def succeeded(self) -> list[Operation]:
        return [op for op in self.operations if op.success is True]


# ---------------------------------------------------------------------------
# Manifest building (no side-effects)
# ---------------------------------------------------------------------------


def _find_source_root(path: Path, config: AppConfig) -> Path:
    """Return the source_dir that is an ancestor of *path*.

    Used to compute the relative path for mirroring directory structure.
    Raises ValueError if no source_dir matches.
    """
    for source_dir in config.source_dirs:
        try:
            path.relative_to(source_dir)
            return source_dir
        except ValueError:
            continue
    raise ValueError(f"Cannot determine source root for {path}")


def _mirror_path(raw_path: Path, source_root: Path, destination_root: Path) -> Path:
    """Compute the mirrored destination path preserving relative directory structure."""
    relative = raw_path.relative_to(source_root)
    return destination_root / relative


def build_manifest(scan_result: ScanResult, config: AppConfig) -> RoutingManifest:
    """Build a RoutingManifest from a ScanResult without touching the filesystem."""
    manifest = RoutingManifest(dry_run=config.dry_run)

    # Paired files
    for pair in scan_result.pairs:
        source_root = _find_source_root(pair.raw, config)

        manifest.operations.append(
            Operation(
                kind=OpKind.COPY_RAW_TO_ARCHIVE,
                source=pair.raw,
                destination=_mirror_path(pair.raw, source_root, config.raw_archive),
            )
        )
        manifest.operations.append(
            Operation(
                kind=OpKind.DELETE_SOURCE_RAW,
                source=pair.raw,
                destination=None,
            )
        )
        manifest.operations.append(
            Operation(
                kind=OpKind.SKIP_JPEG,
                source=pair.jpeg,
                destination=None,
            )
        )

    # Orphan RAWs
    for orphan in scan_result.orphan_raws:
        source_root = _find_source_root(orphan.raw, config)

        manifest.operations.append(
            Operation(
                kind=OpKind.COPY_RAW_TO_QUEUE,
                source=orphan.raw,
                destination=_mirror_path(orphan.raw, source_root, config.piece2_queue),
            )
        )
        manifest.operations.append(
            Operation(
                kind=OpKind.DELETE_SOURCE_RAW,
                source=orphan.raw,
                destination=None,
            )
        )

    # Orphan JPEGs — intentionally no operations generated

    return manifest


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _execute_pair_copy(copy_op: Operation, delete_op: Operation) -> tuple[Operation, Operation]:
    """Copy RAW to destination then delete source. Delete only runs on copy success."""
    assert copy_op.destination is not None

    try:
        copy_op.destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(copy_op.source, copy_op.destination)
        copy_op.success = True
    except OSError as exc:
        copy_op.success = False
        copy_op.error = str(exc)
        delete_op.success = False
        delete_op.error = "Skipped: copy failed"
        return copy_op, delete_op

    # Delete only after confirmed copy
    try:
        copy_op.source.unlink()
        delete_op.success = True
    except OSError as exc:
        delete_op.success = False
        delete_op.error = str(exc)

    return copy_op, delete_op


def execute(manifest: RoutingManifest, workers: int = 4) -> RoutingManifest:
    """Execute all operations in the manifest.

    If manifest.dry_run is True this is a no-op — operations remain pending.
    Delete operations always run after their paired copy in the same thread.
    """
    if manifest.dry_run:
        return manifest

    # Build (copy_op, delete_op) pairs for parallel execution.
    # SKIP_JPEG ops are marked successful immediately — nothing to do.
    for op in manifest.skipped_jpegs:
        op.success = True

    # Pair up copy → delete operations by source path
    copy_ops: dict[Path, Operation] = {}
    delete_ops: dict[Path, Operation] = {}

    for op in manifest.operations:
        if op.kind in (OpKind.COPY_RAW_TO_ARCHIVE, OpKind.COPY_RAW_TO_QUEUE):
            copy_ops[op.source] = op
        elif op.kind == OpKind.DELETE_SOURCE_RAW:
            delete_ops[op.source] = op

    tasks = [(copy_op, delete_ops[src]) for src, copy_op in copy_ops.items() if src in delete_ops]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_execute_pair_copy, copy_op, del_op): (copy_op, del_op)
            for copy_op, del_op in tasks
        }
        for future in as_completed(futures):
            # Results are already written back into the Operation objects
            future.result()

    return manifest


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


def route(scan_result: ScanResult, config: AppConfig) -> RoutingManifest:
    """Build manifest and execute (or simulate if dry_run=True)."""
    manifest = build_manifest(scan_result, config)
    return execute(manifest, workers=config.workers)
