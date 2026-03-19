"""Scanner — walks source directories and classifies files into pairs and orphans.

All logic here is pure filesystem inspection with zero side-effects.
No files are moved, copied, or deleted by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import AppConfig

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilePair:
    """A matched RAW + JPEG sharing the same directory and filename stem."""

    raw: Path
    jpeg: Path
    stem: str

    @property
    def directory(self) -> Path:
        return self.raw.parent


@dataclass(frozen=True)
class OrphanRaw:
    """A RAW file with no matching JPEG in the same directory."""

    raw: Path
    stem: str

    @property
    def directory(self) -> Path:
        return self.raw.parent


@dataclass(frozen=True)
class OrphanJpeg:
    """A JPEG file with no matching RAW in the same directory."""

    jpeg: Path
    stem: str

    @property
    def directory(self) -> Path:
        return self.jpeg.parent


@dataclass
class ScanResult:
    """Aggregated results from scanning one or more source directories."""

    pairs: list[FilePair] = field(default_factory=list)
    orphan_raws: list[OrphanRaw] = field(default_factory=list)
    orphan_jpegs: list[OrphanJpeg] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience counts
    # ------------------------------------------------------------------

    @property
    def total_files(self) -> int:
        return len(self.pairs) * 2 + len(self.orphan_raws) + len(self.orphan_jpegs)

    @property
    def total_raws(self) -> int:
        return len(self.pairs) + len(self.orphan_raws)

    @property
    def total_jpegs(self) -> int:
        return len(self.pairs) + len(self.orphan_jpegs)


# ---------------------------------------------------------------------------
# Core scanning logic
# ---------------------------------------------------------------------------


def _scan_directory(directory: Path, config: AppConfig) -> ScanResult:
    """Recursively scan a single directory tree and classify all photo files."""
    result = ScanResult()

    if not directory.exists():
        result.errors.append(f"Source directory does not exist: {directory}")
        return result

    if not directory.is_dir():
        result.errors.append(f"Source path is not a directory: {directory}")
        return result

    # Walk the directory tree, processing each directory independently.
    # Using os.walk via Path.rglob would mix files from different dirs;
    # instead we group by parent so pairing is always within one directory.
    dirs_seen: set[Path] = set()
    all_photo_files: dict[Path, list[Path]] = {}

    for file_path in sorted(directory.rglob("*")):
        if not file_path.is_file():
            continue
        if not (config.is_raw(file_path) or config.is_jpeg(file_path)):
            continue

        parent = file_path.parent
        if parent not in all_photo_files:
            all_photo_files[parent] = []
            dirs_seen.add(parent)
        all_photo_files[parent].append(file_path)

    # Process each directory independently
    for _dir_path, files in all_photo_files.items():
        dir_result = _classify_directory_files(files, config)
        result.pairs.extend(dir_result.pairs)
        result.orphan_raws.extend(dir_result.orphan_raws)
        result.orphan_jpegs.extend(dir_result.orphan_jpegs)
        result.errors.extend(dir_result.errors)

    return result


def _classify_directory_files(files: list[Path], config: AppConfig) -> ScanResult:
    """Classify a flat list of files (all from the same directory) into pairs and orphans.

    Matching is case-insensitive on both stem and extension.
    If multiple RAW formats match the same stem, the first found is used and
    the remainder are treated as orphan RAWs.
    """
    result = ScanResult()

    # Build stem → {raw: Path | None, jpeg: Path | None} index
    # Key is lowercase stem for case-insensitive matching
    index: dict[str, dict[str, Path | None]] = {}

    for file_path in files:
        stem_lower = file_path.stem.lower()
        if stem_lower not in index:
            index[stem_lower] = {"raw": None, "jpeg": None}

        if config.is_raw(file_path):
            if index[stem_lower]["raw"] is not None:
                # Duplicate RAW stem (e.g. both .ARW and .NEF — unusual but possible)
                result.orphan_raws.append(OrphanRaw(raw=file_path, stem=file_path.stem))
            else:
                index[stem_lower]["raw"] = file_path

        elif config.is_jpeg(file_path):
            if index[stem_lower]["jpeg"] is not None:
                # Duplicate JPEG stem (e.g. both .JPG and .JPEG)
                result.orphan_jpegs.append(OrphanJpeg(jpeg=file_path, stem=file_path.stem))
            else:
                index[stem_lower]["jpeg"] = file_path

    # Classify each stem
    for _stem_lower, entry in index.items():
        raw = entry["raw"]
        jpeg = entry["jpeg"]

        if raw is not None and jpeg is not None:
            result.pairs.append(FilePair(raw=raw, jpeg=jpeg, stem=raw.stem))
        elif raw is not None:
            result.orphan_raws.append(OrphanRaw(raw=raw, stem=raw.stem))
        elif jpeg is not None:
            result.orphan_jpegs.append(OrphanJpeg(jpeg=jpeg, stem=jpeg.stem))

    return result


def scan(config: AppConfig) -> ScanResult:
    """Scan all configured source directories and return a unified ScanResult."""
    combined = ScanResult()

    for source_dir in config.source_dirs:
        result = _scan_directory(source_dir, config)
        combined.pairs.extend(result.pairs)
        combined.orphan_raws.extend(result.orphan_raws)
        combined.orphan_jpegs.extend(result.orphan_jpegs)
        combined.errors.extend(result.errors)

    return combined
