"""photo-router — FastAPI service.

Endpoints:
  GET  /              — UI (preview page)
  POST /api/scan      — scan source dirs, return manifest preview
  POST /api/execute   — execute the routing (dry_run must be false in config)
  GET  /api/config    — return current config (redacted paths only)
  GET  /api/health    — health check
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import AppConfig, load_config
from app.router import RoutingManifest, build_manifest, execute
from app.scanner import ScanResult, scan

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="photo-router", version="0.1.0")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

CONFIG_PATH = Path(os.environ.get("PHOTO_ROUTER_CONFIG", "config.yaml"))


def _get_config() -> AppConfig:
    try:
        return load_config(CONFIG_PATH)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Config error: {exc}") from exc


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialise_manifest(manifest: RoutingManifest, scan_result: ScanResult) -> dict:
    def _op(op):
        return {
            "kind": op.kind.name,
            "source": str(op.source),
            "destination": str(op.destination) if op.destination else None,
            "success": op.success,
            "error": op.error,
        }

    return {
        "dry_run": manifest.dry_run,
        "summary": {
            "pairs_found": len(scan_result.pairs),
            "orphan_raws": len(scan_result.orphan_raws),
            "orphan_jpegs": len(scan_result.orphan_jpegs),
            "copies_to_archive": len(manifest.copies_to_archive),
            "copies_to_queue": len(manifest.copies_to_queue),
            "skipped_jpegs": len(manifest.skipped_jpegs),
            "deletes": len(manifest.deletes),
            "failed": len(manifest.failed),
            "scan_errors": scan_result.errors,
        },
        "operations": [_op(op) for op in manifest.operations],
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def get_config():
    cfg = _get_config()
    return {
        "source_dirs": [str(d) for d in cfg.source_dirs],
        "raw_archive": str(cfg.raw_archive),
        "piece2_queue": str(cfg.piece2_queue),
        "raw_extensions": sorted(cfg.raw_extensions),
        "jpeg_extensions": sorted(cfg.jpeg_extensions),
        "dry_run": cfg.dry_run,
        "workers": cfg.workers,
    }


@app.post("/api/scan")
def api_scan():
    """Scan source directories and return the manifest preview.

    Always runs in manifest-build mode (no files touched regardless of dry_run).
    """
    cfg = _get_config()
    result = scan(cfg)
    manifest = build_manifest(result, cfg)
    return _serialise_manifest(manifest, result)


@app.post("/api/execute")
def api_execute():
    """Execute the routing operations.

    Requires dry_run=false in config.yaml — returns 400 otherwise.
    """
    cfg = _get_config()
    if cfg.dry_run:
        raise HTTPException(
            status_code=400,
            detail="dry_run is true in config.yaml — set it to false to execute.",
        )
    result = scan(cfg)
    manifest = build_manifest(result, cfg)
    execute(manifest, workers=cfg.workers)
    return _serialise_manifest(manifest, result)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
