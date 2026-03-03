"""Change detection: SHA256 checksums, stale detection, shared tag scanning."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from manifest import Manifest, ShareEntry, Target


SHARED_TAG = "<!-- shared -->"


@dataclass
class ChangeReport:
    stale: list[tuple[ShareEntry, Target, str]]  # entry, target, new_checksum
    source_missing: list[ShareEntry]
    untracked_shared: list[Path]  # files with <!-- shared --> tag not in manifest
    ok: list[tuple[ShareEntry, Target]]
    warnings: list[str]


def compute_checksum(file_path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def has_shared_tag(file_path: Path) -> bool:
    """Check if a file contains <!-- shared --> anywhere in it."""
    try:
        with open(file_path) as f:
            for line in f:
                if SHARED_TAG in line:
                    return True
    except (OSError, UnicodeDecodeError):
        pass
    return False


def check_changes(manifest: Manifest, workspace_root: Path) -> ChangeReport:
    """Compare manifest checksums against current source files."""
    stale = []
    source_missing = []
    ok = []
    warnings = []

    tracked_sources = set()

    for entry in manifest.shares:
        source_path = workspace_root / entry.source

        if not source_path.exists():
            if entry.status != "source_missing":
                warnings.append(f"Source missing: {entry.source}")
            source_missing.append(entry)
            tracked_sources.add(entry.source)
            continue

        # Skip directory entries (like subtree references)
        if source_path.is_dir():
            tracked_sources.add(entry.source)
            continue

        tracked_sources.add(entry.source)
        current_checksum = compute_checksum(source_path)

        for target in entry.targets:
            if target.type == "subtree":
                continue
            if not target.last_synced:
                # Never pushed yet — always stale
                stale.append((entry, target, current_checksum))
            elif target.source_checksum and target.source_checksum != current_checksum:
                # Source changed since last push
                stale.append((entry, target, current_checksum))
            else:
                ok.append((entry, target))

    # Scan for untracked files with <!-- shared --> tag
    untracked = _scan_untracked_shared(workspace_root, tracked_sources)

    return ChangeReport(
        stale=stale,
        source_missing=source_missing,
        untracked_shared=untracked,
        ok=ok,
        warnings=warnings,
    )


def _scan_untracked_shared(
    workspace_root: Path, tracked_sources: set[str]
) -> list[Path]:
    """Find .md files with <!-- shared --> tag that aren't in the manifest."""
    untracked = []
    # Scan common content directories
    scan_dirs = [
        workspace_root / "syntea-pm" / "department-context",
        workspace_root / "syntea-pm" / "context",
        workspace_root / "context",
    ]
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for md_file in scan_dir.rglob("*.md"):
            rel = str(md_file.relative_to(workspace_root))
            if rel not in tracked_sources and has_shared_tag(md_file):
                untracked.append(md_file)
    return untracked
