from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_CENTER_DIST = REPO_ROOT / "frontend" / "control-center" / "dist"


def control_center_index_path(dist_dir: Path | None = None) -> Path | None:
    root = dist_dir or CONTROL_CENTER_DIST
    index_path = root / "index.html"
    return index_path if index_path.is_file() else None


def control_center_static_path(asset_path: str, dist_dir: Path | None = None) -> Path | None:
    root = (dist_dir or CONTROL_CENTER_DIST).resolve()
    candidate = (root / asset_path.lstrip("/")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None
