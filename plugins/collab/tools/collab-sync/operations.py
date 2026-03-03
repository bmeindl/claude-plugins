"""File operations: copy with frontmatter, directory creation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def copy_with_frontmatter(
    source: Path,
    dest: Path,
    shared_from: str,
    tag: str = "",
    encrypt_for: str = "",
    workspace: Path | None = None,
) -> None:
    """Copy a file to destination, prepending sharing frontmatter.

    If encrypt_for is set, the combined frontmatter+content is age-encrypted
    and written as binary. The dest should end in .age for encrypted files.
    """
    content = source.read_text()
    now = datetime.utcnow().strftime("%Y-%m-%d")

    frontmatter = f"---\nshared_from: {shared_from}\nshared_at: {now}\n---\n"
    if tag:
        frontmatter += f"<!-- tag: {tag} -->\n\n"
    else:
        frontmatter += "\n"

    combined = frontmatter + content

    dest.parent.mkdir(parents=True, exist_ok=True)

    if encrypt_for and workspace:
        import crypto
        ciphertext = crypto.encrypt_for_peer(combined.encode("utf-8"), workspace, encrypt_for)
        dest.write_bytes(ciphertext)
    else:
        dest.write_text(combined)


def copy_raw(source: Path, dest: Path) -> None:
    """Copy a file without modification."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(source.read_text())


def ensure_directory(path: Path) -> None:
    """Create directory and parents if needed."""
    path.mkdir(parents=True, exist_ok=True)
