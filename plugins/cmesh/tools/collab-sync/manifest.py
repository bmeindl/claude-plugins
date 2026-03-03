"""Manifest loading, saving, and validation for .collab-manifest.yml."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


MANIFEST_FILENAME = ".collab-manifest.yml"
MANIFEST_VERSION = 1


@dataclass
class Target:
    repo: str
    dest: str
    visibility: str
    last_synced: str = ""
    source_checksum: str = ""
    tag: str = ""
    type: str = "copy"  # copy | subtree
    note: str = ""
    encrypt_for: str = ""  # empty = plaintext, person name = age-encrypted


@dataclass
class ShareEntry:
    source: str
    status: str = "active"  # active | source_missing | paused
    targets: list[Target] = field(default_factory=list)


@dataclass
class Manifest:
    version: int = MANIFEST_VERSION
    workspace: str = ""
    user: str = ""
    ai_collab_path: str = ""  # deprecated, kept for backward compat
    repos: dict[str, str] = field(default_factory=dict)  # name → relative path
    shares: list[ShareEntry] = field(default_factory=list)


def load(workspace_root: Path) -> Manifest:
    """Load manifest from workspace root. Returns empty manifest if not found."""
    manifest_path = workspace_root / MANIFEST_FILENAME
    if not manifest_path.exists():
        return Manifest()

    with open(manifest_path) as f:
        data = yaml.safe_load(f) or {}

    return _parse(data)


def save(manifest: Manifest, workspace_root: Path) -> Path:
    """Save manifest to workspace root. Atomic write via temp file. Returns path written."""
    import os

    manifest_path = workspace_root / MANIFEST_FILENAME
    tmp_path = manifest_path.with_suffix(".yml.tmp")
    data = _serialize(manifest)

    with open(tmp_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    os.rename(tmp_path, manifest_path)
    return manifest_path


def find_entry(manifest: Manifest, source: str) -> ShareEntry | None:
    """Find a share entry by source path."""
    for entry in manifest.shares:
        if entry.source == source:
            return entry
    return None


def add_entry(
    manifest: Manifest,
    source: str,
    repo: str,
    dest: str,
    visibility: str,
    checksum: str,
    tag: str,
    encrypt_for: str = "",
) -> ShareEntry:
    """Add a new share entry to the manifest."""
    target = Target(
        repo=repo,
        dest=dest,
        visibility=visibility,
        last_synced="",  # Only set by push after successful sync
        source_checksum=checksum,
        tag=tag,
        encrypt_for=encrypt_for,
    )
    entry = find_entry(manifest, source)
    if entry:
        # Add target to existing entry
        entry.targets.append(target)
    else:
        entry = ShareEntry(source=source, targets=[target])
        manifest.shares.append(entry)
    return entry


def remove_entry(manifest: Manifest, source: str, repo: str | None = None) -> bool:
    """Remove a share entry (or a specific target within it). Returns True if found."""
    for i, entry in enumerate(manifest.shares):
        if entry.source == source:
            if repo:
                entry.targets = [t for t in entry.targets if t.repo != repo]
                if not entry.targets:
                    manifest.shares.pop(i)
            else:
                manifest.shares.pop(i)
            return True
    return False


def _parse(data: dict[str, Any]) -> Manifest:
    shares = []
    for s in data.get("shares", []):
        targets = []
        for t in s.get("targets", []):
            targets.append(Target(
                repo=t.get("repo", ""),
                dest=t.get("dest", ""),
                visibility=t.get("visibility", ""),
                last_synced=t.get("last_synced", ""),
                source_checksum=t.get("source_checksum", ""),
                tag=t.get("tag", ""),
                type=t.get("type", "copy"),
                note=t.get("note", ""),
                encrypt_for=t.get("encrypt_for", ""),
            ))
        shares.append(ShareEntry(
            source=s.get("source", ""),
            status=s.get("status", "active"),
            targets=targets,
        ))
    # Backward compat: migrate ai_collab_path → repos dict
    if "repos" in data:
        repos = data["repos"]
    elif data.get("ai_collab_path"):
        repos = {"ai-collab": data["ai_collab_path"]}
    else:
        repos = {"ai-collab": "../ai-collab"}

    return Manifest(
        version=data.get("version", MANIFEST_VERSION),
        workspace=data.get("workspace", ""),
        user=data.get("user", ""),
        ai_collab_path=data.get("ai_collab_path", ""),
        repos=repos,
        shares=shares,
    )


def _serialize(manifest: Manifest) -> dict[str, Any]:
    shares = []
    for entry in manifest.shares:
        targets = []
        for t in entry.targets:
            td: dict[str, Any] = {"repo": t.repo}
            if t.type != "copy":
                td["type"] = t.type
            if t.dest:
                td["dest"] = t.dest
            if t.visibility:
                td["visibility"] = t.visibility
            if t.last_synced:
                td["last_synced"] = t.last_synced
            if t.source_checksum:
                td["source_checksum"] = t.source_checksum
            if t.tag:
                td["tag"] = t.tag
            if t.note:
                td["note"] = t.note
            if t.encrypt_for:
                td["encrypt_for"] = t.encrypt_for
            targets.append(td)
        shares.append({
            "source": entry.source,
            "status": entry.status,
            "targets": targets,
        })
    result: dict[str, Any] = {
        "version": manifest.version,
        "workspace": manifest.workspace,
        "user": manifest.user,
    }
    if manifest.repos:
        result["repos"] = manifest.repos
    # Backward compat: keep ai_collab_path if it was set
    if manifest.ai_collab_path:
        result["ai_collab_path"] = manifest.ai_collab_path
    result["shares"] = shares
    return result
