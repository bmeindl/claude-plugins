"""Safety checks: private tags, .collabignore parsing, source validation."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path


PRIVATE_TAG = "<!-- private -->"
COLLABIGNORE_FILENAME = ".collabignore"


def is_private(file_path: Path) -> bool:
    """Check if a file has <!-- private --> as its first line. Deterministic — cannot be overridden."""
    try:
        with open(file_path) as f:
            first_line = f.readline().strip()
        return first_line == PRIVATE_TAG
    except (OSError, UnicodeDecodeError):
        return False


def is_ignored(file_path: Path, workspace_root: Path) -> bool:
    """Check if a file is excluded by any .collabignore in its directory tree."""
    rel = file_path.relative_to(workspace_root)
    patterns = _collect_ignore_patterns(file_path.parent, workspace_root)
    rel_str = str(rel)
    filename = file_path.name

    for pattern, negated in patterns:
        if negated:
            if fnmatch(filename, pattern) or fnmatch(rel_str, pattern):
                return False  # Exception — include this file
        else:
            if pattern == "*":
                return True
            if fnmatch(filename, pattern) or fnmatch(rel_str, pattern):
                return True
    return False


def source_exists(file_path: Path) -> bool:
    """Check if source file exists."""
    return file_path.is_file()


def check_file_safety(file_path: Path, workspace_root: Path) -> str | None:
    """Run all safety checks on a file. Returns error message or None if safe."""
    if not source_exists(file_path):
        return f"Source file missing: {file_path}"
    if is_private(file_path):
        return f"File is marked private (<!-- private --> tag): {file_path}"
    if is_ignored(file_path, workspace_root):
        return f"File is excluded by .collabignore: {file_path}"
    return None


def _collect_ignore_patterns(
    directory: Path, workspace_root: Path
) -> list[tuple[str, bool]]:
    """Collect all .collabignore patterns from directory up to workspace root."""
    patterns: list[tuple[str, bool]] = []
    current = directory

    while True:
        ignore_file = current / COLLABIGNORE_FILENAME
        if ignore_file.is_file():
            patterns.extend(_parse_collabignore(ignore_file))

        if current == workspace_root:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    return patterns


def _parse_collabignore(path: Path) -> list[tuple[str, bool]]:
    """Parse a .collabignore file. Returns list of (pattern, is_negated)."""
    patterns = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                patterns.append((line[1:], True))
            else:
                patterns.append((line, False))
    return patterns
