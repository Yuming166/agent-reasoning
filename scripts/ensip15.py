"""Small offline bridge to the pinned ENSIP-15 JavaScript normalizer."""
from __future__ import annotations

import functools
import subprocess
from pathlib import Path

NORMALIZER_PACKAGE = "@adraffy/ens-normalize"
NORMALIZER_VERSION = "1.11.1"


@functools.lru_cache(maxsize=4096)
def ensip15_normalize(name: str, project_root: str | Path | None = None) -> str:
    """Return the ENSIP-15-normalized name or fail closed when unavailable/invalid."""
    value = (name or "").strip()
    if not value:
        raise ValueError("ENS name is empty")
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[1]
    helper = root / "scripts/ens_normalize_name.cjs"
    try:
        result = subprocess.run(
            ["node", str(helper), value], check=False, capture_output=True,
            text=True, encoding="utf-8", timeout=10,
            cwd=root,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"ENSIP-15 normalizer unavailable; run npm ci in {root} "
            f"({NORMALIZER_PACKAGE}@{NORMALIZER_VERSION})"
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.strip()[:300]
        raise ValueError(f"ENSIP-15 rejected name: {detail or 'normalization failed'}")
    normalized = result.stdout
    if not normalized:
        raise ValueError("ENSIP-15 produced an empty name")
    return normalized
