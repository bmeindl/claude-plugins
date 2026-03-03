#!/usr/bin/env python3
"""collab-sync — Deterministic sync tool for .collab-manifest.yml.

Usage:
    collab-sync check                 Report stale/missing shares (read-only)
    collab-sync check --summary       Short summary for status display
    collab-sync push                  Copy changed files to target, commit, push
    collab-sync push --dry            Show what would happen, don't act
    collab-sync add <file>            Add a file to manifest
    collab-sync remove <source>       Remove a share entry
    collab-sync connect <name>        Fetch and store peer's public keys for encryption
    collab-sync pull                  Decrypt inbound .age files
    collab-sync list                  Show connected peers, shared files, encryption state
    collab-sync init                  Create manifest from scratch

Reads .collab-manifest.yml from the workspace root (auto-detected or --workspace).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import manifest
import changes
import operations
import safety


def find_workspace_root(start: Path | None = None) -> Path:
    """Walk up from start (or cwd) to find a directory containing .collab-manifest.yml or .git."""
    current = start or Path.cwd()
    while True:
        if (current / manifest.MANIFEST_FILENAME).exists():
            return current
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    print("Error: Could not find workspace root (no .git or .collab-manifest.yml found)", file=sys.stderr)
    sys.exit(1)


def resolve_repo(workspace_root: Path, m: manifest.Manifest, repo_name: str) -> Path:
    """Resolve a named repo to its local path. Exits on error."""
    rel = m.repos.get(repo_name)
    if not rel:
        print(f"Error: Unknown repo '{repo_name}'. Configured: {list(m.repos.keys())}", file=sys.stderr)
        sys.exit(1)
    path = (workspace_root / rel).resolve()
    if not path.is_dir():
        print(f"Error: Repo '{repo_name}' not found at {path}", file=sys.stderr)
        sys.exit(1)
    return path


def resolve_all_repos(workspace_root: Path, m: manifest.Manifest) -> dict[str, Path]:
    """Resolve all configured repos. Warns and skips missing ones."""
    resolved: dict[str, Path] = {}
    for name, rel in m.repos.items():
        path = (workspace_root / rel).resolve()
        if path.is_dir():
            resolved[name] = path
        else:
            print(f"Warning: Repo '{name}' not found at {path}. Skipping.", file=sys.stderr)
    return resolved


# --- Commands ---


def cmd_check(args: argparse.Namespace) -> None:
    workspace = find_workspace_root(Path(args.workspace) if args.workspace else None)
    m = manifest.load(workspace)
    if not m.shares:
        print("No shares in manifest.")
        return

    report = changes.check_changes(m, workspace)

    if args.summary:
        total = len(report.ok) + len(report.stale)
        print(f"Shares: {total + len(report.source_missing)} total")
        print(f"  OK: {len(report.ok)}")
        print(f"  Stale: {len(report.stale)}")
        print(f"  Source missing: {len(report.source_missing)}")
        if report.untracked_shared:
            print(f"  Untracked <!-- shared --> files: {len(report.untracked_shared)}")
        return

    if args.json:
        _print_check_json(report, workspace)
        return

    # Human-readable output
    if report.stale:
        print(f"\n## Stale ({len(report.stale)} files changed since last share)")
        for entry, target, new_checksum in report.stale:
            print(f"  {entry.source} → {target.dest}")

    if report.source_missing:
        print(f"\n## Source Missing ({len(report.source_missing)})")
        for entry in report.source_missing:
            print(f"  {entry.source}")

    if report.untracked_shared:
        print(f"\n## Untracked <!-- shared --> files ({len(report.untracked_shared)})")
        for p in report.untracked_shared:
            print(f"  {p.relative_to(workspace)}")

    if report.ok:
        print(f"\n## Up to date ({len(report.ok)})")
        for entry, target in report.ok:
            print(f"  {entry.source} → {target.dest}")

    for w in report.warnings:
        print(f"\n⚠ {w}")

    if not report.stale and not report.source_missing and not report.untracked_shared:
        print("\nAll shares up to date.")


def cmd_push(args: argparse.Namespace) -> None:
    workspace = find_workspace_root(Path(args.workspace) if args.workspace else None)
    m = manifest.load(workspace)
    if not m.shares:
        print("No shares in manifest. Nothing to push.")
        return

    report = changes.check_changes(m, workspace)
    if not report.stale:
        print("Nothing to push — all shares up to date.")
        return

    # Group stale entries by target repo (skip entries targeting unknown repos)
    by_repo: dict[str, list[tuple[manifest.ShareEntry, manifest.Target, str]]] = {}
    for entry, target, checksum in report.stale:
        if target.repo not in m.repos:
            print(f"Warning: Skipping {entry.source} — repo '{target.repo}' not configured.", file=sys.stderr)
            continue
        by_repo.setdefault(target.repo, []).append((entry, target, checksum))

    if not by_repo:
        print("Nothing to push — all stale entries target unknown repos.")
        return

    # Resolve and check each target repo is clean
    repo_paths: dict[str, Path] = {}
    for repo_name in by_repo:
        repo_path = resolve_repo(workspace, m, repo_name)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path, capture_output=True, text=True,
        )
        if result.stdout.strip():
            print(f"Error: Repo '{repo_name}' has uncommitted changes. Commit or stash first.", file=sys.stderr)
            sys.exit(1)
        repo_paths[repo_name] = repo_path

    # Pre-flight: check all required encryption keys exist before touching files
    import crypto

    missing_keys: list[str] = []
    for entry, target, _ in report.stale:
        if target.encrypt_for and not crypto.peer_keys_exist(workspace, target.encrypt_for):
            missing_keys.append(target.encrypt_for)
    if missing_keys:
        unique = sorted(set(missing_keys))
        for peer in unique:
            print(
                f"Error: No keys for '{peer}'. "
                f"Run: collab-sync connect {peer} --github <username>",
                file=sys.stderr,
            )
        sys.exit(1)

    # Process stale files
    pushed: list[tuple[manifest.ShareEntry, manifest.Target, str]] = []
    for entry, target, new_checksum in report.stale:
        source_path = workspace / entry.source
        repo_path = repo_paths[target.repo]
        dest_path = repo_path / target.dest

        # Safety checks
        err = safety.check_file_safety(source_path, workspace)
        if err:
            print(f"Skipping {entry.source}: {err}")
            continue

        if args.dry:
            enc_label = f" [encrypted for {target.encrypt_for}]" if target.encrypt_for else ""
            print(f"Would copy: {entry.source} → {target.repo}:{target.dest}{enc_label}")
            pushed.append((entry, target, new_checksum))
            continue

        operations.copy_with_frontmatter(
            source=source_path,
            dest=dest_path,
            shared_from=entry.source,
            tag=target.tag,
            encrypt_for=target.encrypt_for,
            workspace=workspace,
        )
        # Update manifest in memory (saved only after successful push)
        target.source_checksum = new_checksum
        target.last_synced = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        pushed.append((entry, target, new_checksum))
        print(f"Copied: {entry.source} → {target.repo}:{target.dest}")

    if args.dry:
        print(f"\nDry run: {len(pushed)} files would be pushed.")
        return

    if not pushed:
        print("No files pushed (all skipped by safety checks).")
        return

    # Git operations — per repo
    pushed_by_repo: dict[str, list[tuple[manifest.ShareEntry, manifest.Target, str]]] = {}
    for entry, target, checksum in pushed:
        pushed_by_repo.setdefault(target.repo, []).append((entry, target, checksum))

    failed_repos: list[str] = []
    for repo_name, items in pushed_by_repo.items():
        repo_path = repo_paths[repo_name]
        try:
            subprocess.run(["git", "pull", "--rebase"], cwd=repo_path, check=True)
            for entry, target, _ in items:
                subprocess.run(["git", "add", str(repo_path / target.dest)], cwd=repo_path, check=True)
            msg = f"sync: update {len(items)} shared files from {m.workspace}"
            subprocess.run(["git", "commit", "-m", msg], cwd=repo_path, check=True)
            subprocess.run(["git", "push"], cwd=repo_path, check=True)
        except subprocess.CalledProcessError as e:
            print(f"\nGit operation failed on '{repo_name}': {e}", file=sys.stderr)
            print(f"Files for '{repo_name}' will be retried on next push.", file=sys.stderr)
            failed_repos.append(repo_name)
            # Restore clean state: checkout the files we copied so repo isn't dirty
            for entry, target, _ in items:
                dest_file = repo_path / target.dest
                if dest_file.exists():
                    subprocess.run(
                        ["git", "checkout", "--", str(dest_file)],
                        cwd=repo_path, capture_output=True,
                    )
            # Revert in-memory manifest updates for this repo's items
            for entry, target, _ in items:
                target.source_checksum = ""
                target.last_synced = ""

    # Save manifest — only items from successful repos have updated checksums
    succeeded = len(pushed) - sum(len(pushed_by_repo[r]) for r in failed_repos)
    if succeeded > 0:
        manifest.save(m, workspace)

    if failed_repos:
        print(f"\nPartial push: {succeeded} succeeded, failed repos: {failed_repos}")
        print("Try: git pull --rebase in failed repos, then re-run collab-sync push.", file=sys.stderr)
    else:
        repos_label = ", ".join(pushed_by_repo.keys())
        print(f"\nPushed {len(pushed)} files to {repos_label}.")


def cmd_add(args: argparse.Namespace) -> None:
    workspace = find_workspace_root(Path(args.workspace) if args.workspace else None)
    source_path = Path(args.file)

    # Resolve to relative path from workspace
    if source_path.is_absolute():
        try:
            source_rel = str(source_path.relative_to(workspace))
        except ValueError:
            print(f"Error: {source_path} is not under workspace {workspace}", file=sys.stderr)
            sys.exit(1)
    else:
        source_rel = str(source_path)
        source_path = workspace / source_rel

    # Safety checks
    err = safety.check_file_safety(source_path, workspace)
    if err:
        print(f"Refused: {err}", file=sys.stderr)
        sys.exit(1)

    checksum = changes.compute_checksum(source_path)

    encrypt_for = args.encrypt_for or ""
    dest = args.dest or ""

    # Auto-append .age to dest if encrypting and not already .age
    if encrypt_for and dest and not dest.endswith(".age"):
        dest += ".age"

    m = manifest.load(workspace)
    repo = args.repo or "ai-collab"
    if repo not in m.repos:
        print(f"Error: Unknown repo '{repo}'. Configured: {list(m.repos.keys())}", file=sys.stderr)
        sys.exit(1)
    manifest.add_entry(
        m,
        source=source_rel,
        repo=repo,
        dest=dest,
        visibility=args.visibility or "iu-public",
        checksum=checksum,
        tag=args.tag or "",
        encrypt_for=encrypt_for,
    )
    manifest.save(m, workspace)
    enc_label = f" [encrypted for {encrypt_for}]" if encrypt_for else ""
    print(f"Added: {source_rel} → {dest or '(dest TBD)'} [{args.visibility or 'iu-public'}]{enc_label}")


def cmd_remove(args: argparse.Namespace) -> None:
    workspace = find_workspace_root(Path(args.workspace) if args.workspace else None)
    m = manifest.load(workspace)
    if manifest.remove_entry(m, args.source, repo=args.repo):
        manifest.save(m, workspace)
        print(f"Removed: {args.source}")
    else:
        print(f"Not found: {args.source}", file=sys.stderr)
        sys.exit(1)


def cmd_init(args: argparse.Namespace) -> None:
    workspace = find_workspace_root(Path(args.workspace) if args.workspace else None)
    manifest_path = workspace / manifest.MANIFEST_FILENAME
    if manifest_path.exists() and not args.force:
        print(f"Manifest already exists at {manifest_path}. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    # Build repos dict
    repos: dict[str, str] = {}
    if args.ai_collab:
        repos["ai-collab"] = args.ai_collab
    else:
        repos["ai-collab"] = "../ai-collab"
    if args.repo:
        for name, path in args.repo:
            repos[name] = path

    m = manifest.Manifest(
        workspace=args.name or workspace.name,
        user=args.user or "",
        repos=repos,
    )
    manifest.save(m, workspace)
    print(f"Created {manifest_path}")


def cmd_connect(args: argparse.Namespace) -> None:
    """Fetch and store a peer's public keys for encryption."""
    import crypto

    workspace = find_workspace_root(Path(args.workspace) if args.workspace else None)
    name = args.name

    keys: list[str] = []

    if args.github:
        print(f"Fetching keys from GitHub user '{args.github}'...")
        keys.extend(crypto.fetch_github_keys(args.github))
    if args.gitlab:
        print(f"Fetching keys from GitLab user '{args.gitlab}'...")
        keys.extend(crypto.fetch_gitlab_keys(args.gitlab))
    if args.ssh_key:
        keys.append(args.ssh_key)
    if args.age_key:
        keys.append(args.age_key)

    if not keys:
        print("Error: No keys found or provided.", file=sys.stderr)
        sys.exit(1)

    # Key fingerprint pinning (TOFU)
    new_fp = crypto.compute_key_fingerprint(keys)
    existing_fp = crypto.load_fingerprint(workspace, name)

    if existing_fp:
        if existing_fp == new_fp:
            print(f"Keys for '{name}' unchanged (fingerprint: {new_fp})")
            return
        else:
            print(
                f"\n{'=' * 60}\n"
                f"WARNING: Keys for '{name}' have CHANGED!\n"
                f"  Previous fingerprint: {existing_fp}\n"
                f"  New fingerprint:      {new_fp}\n"
                f"\n"
                f"  This could indicate a compromised account.\n"
                f"  Use --force to accept the new keys.\n"
                f"{'=' * 60}",
                file=sys.stderr,
            )
            if not args.force:
                sys.exit(1)
            print(f"--force used: accepting new keys for '{name}'.")

    key_file = crypto.store_peer_keys(workspace, name, keys)
    crypto.store_fingerprint(workspace, name, new_fp)

    if existing_fp:
        print(f"Updated {len(keys)} key(s) for '{name}' at {key_file} (fingerprint: {new_fp})")
    else:
        print(f"Connected '{name}' — stored {len(keys)} key(s) (fingerprint: {new_fp})")

    # Validate usability
    usable = [k for k in keys if k.startswith("ssh-ed25519 ") or k.startswith("age1")]
    rsa_only = [k for k in keys if k.startswith("ssh-rsa ")]

    if not usable:
        print(f"\nWarning: No usable keys for encryption (age needs ssh-ed25519 or age1... keys).", file=sys.stderr)
        if rsa_only:
            print(f"  Found {len(rsa_only)} ssh-rsa key(s) — these are NOT supported by age.", file=sys.stderr)
            print(f"  Ask '{name}' to add an ssh-ed25519 key to their GitHub/GitLab profile.", file=sys.stderr)
    else:
        print(f"  {len(usable)} usable key(s) for encryption.")


def cmd_pull(args: argparse.Namespace) -> None:
    """Decrypt inbound .age files from all configured repos."""
    import crypto

    workspace = find_workspace_root(Path(args.workspace) if args.workspace else None)
    m = manifest.load(workspace)
    repos = resolve_all_repos(workspace, m)

    if not repos:
        print("Error: No repos configured or available.", file=sys.stderr)
        sys.exit(1)

    user = m.user
    if not user:
        print("Error: No 'user' set in manifest. Run: collab-sync init --user <name>", file=sys.stderr)
        sys.exit(1)

    # Fetch latest from each repo, then scan for .age files
    age_files: list[tuple[str, Path, Path]] = []  # (sender, age_file, repo_path)
    for repo_name, repo_path in repos.items():
        try:
            subprocess.run(["git", "pull"], cwd=repo_path, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Warning: git pull failed for '{repo_name}' ({e}). Using local copy.", file=sys.stderr)

        for sender_dir in repo_path.iterdir():
            if not sender_dir.is_dir() or sender_dir.name.startswith("."):
                continue
            sender = sender_dir.name
            if sender == user:
                continue
            outbound_for_us = sender_dir / "outbound" / user
            if not outbound_for_us.is_dir():
                continue
            for age_file in outbound_for_us.rglob("*.age"):
                age_files.append((sender, age_file, repo_path))

    if not age_files:
        print("No encrypted files found for you.")
        return

    inbound_base = workspace / "shared-context" / "inbound"
    identity_path = args.identity if args.identity else None
    decrypted = 0
    errors = 0

    for sender, age_file, repo_path in age_files:
        rel = age_file.relative_to(repo_path / sender / "outbound" / user)
        out_name = str(rel)
        if out_name.endswith(".age"):
            out_name = out_name[:-4]
        dest = inbound_base / sender / out_name

        if args.dry:
            print(f"Would decrypt: {sender}/outbound/{user}/{rel} → shared-context/inbound/{sender}/{out_name}")
            decrypted += 1
            continue

        try:
            ciphertext = age_file.read_bytes()
            plaintext = crypto.decrypt_with_identity(ciphertext, identity_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(plaintext)
            print(f"Decrypted: {sender}/{rel.name} → inbound/{sender}/{out_name}")
            decrypted += 1
        except Exception as e:
            print(f"Failed to decrypt {age_file.name}: {e}", file=sys.stderr)
            errors += 1

    if args.dry:
        print(f"\nDry run: {decrypted} file(s) would be decrypted.")
    else:
        print(f"\nDecrypted {decrypted} file(s), {errors} error(s).")


def cmd_list(args: argparse.Namespace) -> None:
    """Show connected peers, shared files, and encryption state."""
    import crypto

    workspace = find_workspace_root(Path(args.workspace) if args.workspace else None)
    m = manifest.load(workspace)

    # --- Peers: scan .collab-keys/*.pub ---
    keys_dir = workspace / crypto.COLLAB_KEYS_DIR
    peers: list[dict] = []
    if keys_dir.is_dir():
        for pub_file in sorted(keys_dir.glob("*.pub")):
            name = pub_file.stem
            if name == "identity":
                continue  # Skip own identity file
            keys = [k.strip() for k in pub_file.read_text().splitlines() if k.strip()]
            usable = [k for k in keys if k.startswith("ssh-ed25519 ") or k.startswith("age1")]
            fp = crypto.load_fingerprint(workspace, name) or ""
            peers.append({
                "name": name,
                "keys": len(keys),
                "usable": len(usable),
                "fingerprint": fp,
            })

    # --- Outbound: iterate manifest shares ---
    outbound: list[dict] = []
    for entry in m.shares:
        for target in entry.targets:
            # Apply filters
            if args.peer and target.visibility != args.peer and target.encrypt_for != args.peer:
                continue
            if args.encrypted_only and not target.encrypt_for:
                continue
            outbound.append({
                "source": entry.source,
                "dest": target.dest,
                "visibility": target.visibility,
                "encrypted": bool(target.encrypt_for),
                "encrypt_for": target.encrypt_for,
                "tag": target.tag,
                "last_synced": target.last_synced,
            })

    # --- Inbound pending: scan all repos for .age files addressed to us ---
    inbound_pending: list[dict] = []
    repos = resolve_all_repos(workspace, m)
    user = m.user
    if user:
        for repo_name, repo_path in repos.items():
            for sender_dir in repo_path.iterdir():
                if not sender_dir.is_dir() or sender_dir.name.startswith("."):
                    continue
                if sender_dir.name == user:
                    continue
                outbound_for_us = sender_dir / "outbound" / user
                if not outbound_for_us.is_dir():
                    continue
                for age_file in outbound_for_us.rglob("*.age"):
                    inbound_pending.append({
                        "sender": sender_dir.name,
                        "file": str(age_file.relative_to(repo_path)),
                        "repo": repo_name,
                    })

    if args.json:
        data = {
            "peers": peers,
            "outbound": outbound,
            "inbound_pending": inbound_pending,
        }
        print(json.dumps(data, indent=2, default=str))
        return

    # --- Human-readable output ---
    if peers:
        print("Connected Peers:")
        for p in peers:
            key_desc = f"{p['usable']} usable" if p['usable'] != p['keys'] else str(p['keys'])
            fp_str = f"fingerprint: {p['fingerprint']}" if p['fingerprint'] else "no fingerprint"
            print(f"  {p['name']:<16} {key_desc} key(s)    {fp_str}")
    else:
        print("Connected Peers: (none)")

    print()

    if outbound:
        print("Outbound Shares:")
        for o in outbound:
            enc = "encrypted" if o["encrypted"] else "plaintext"
            synced = o["last_synced"][:10] if o["last_synced"] else "never"
            tag_str = f'  "{o["tag"]}"' if o["tag"] else ""
            dest_label = o["encrypt_for"] or o["visibility"]
            print(f"  {o['source']:<40} → {dest_label:<12} {enc:<10} synced {synced}{tag_str}")
    else:
        filter_note = f" (filter: {args.peer})" if args.peer else ""
        print(f"Outbound Shares: (none){filter_note}")

    print()

    if inbound_pending:
        print(f"Inbound (pending decrypt): {len(inbound_pending)} file(s)")
        for ip in inbound_pending:
            print(f"  from {ip['sender']}: {ip['file']}")
    else:
        print("Inbound (pending decrypt): (none)")


def _print_check_json(report: changes.ChangeReport, workspace: Path) -> None:
    data = {
        "stale": [
            {"source": e.source, "dest": t.dest, "new_checksum": c}
            for e, t, c in report.stale
        ],
        "source_missing": [e.source for e in report.source_missing],
        "untracked_shared": [str(p.relative_to(workspace)) for p in report.untracked_shared],
        "ok": [{"source": e.source, "dest": t.dest} for e, t in report.ok],
        "warnings": report.warnings,
    }
    print(json.dumps(data, indent=2))


# --- CLI ---


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="collab-sync",
        description="Deterministic sync tool for .collab-manifest.yml",
    )
    parser.add_argument("--workspace", help="Workspace root (auto-detected if omitted)")
    sub = parser.add_subparsers(dest="command", required=True)

    # check
    p_check = sub.add_parser("check", help="Report stale/missing shares")
    p_check.add_argument("--summary", action="store_true", help="Short summary")
    p_check.add_argument("--json", action="store_true", help="JSON output")

    # push
    p_push = sub.add_parser("push", help="Copy changed files to target, commit, push")
    p_push.add_argument("--dry", action="store_true", help="Dry run")

    # add
    p_add = sub.add_parser("add", help="Add a file to manifest")
    p_add.add_argument("file", help="Source file path")
    p_add.add_argument("--dest", help="Destination path in target repo")
    p_add.add_argument("--repo", default="ai-collab", help="Target repo name")
    p_add.add_argument("--visibility", default="iu-public", help="Visibility level")
    p_add.add_argument("--tag", default="", help="Description tag")
    p_add.add_argument("--encrypt-for", default="", help="Peer name to encrypt for (requires connect first)")

    # remove
    p_remove = sub.add_parser("remove", help="Remove a share entry")
    p_remove.add_argument("source", help="Source path to remove")
    p_remove.add_argument("--repo", help="Remove only for this target repo")

    # connect
    p_connect = sub.add_parser("connect", help="Fetch and store peer's public keys")
    p_connect.add_argument("name", help="Peer name (e.g., 'quintus')")
    p_connect.add_argument("--github", help="GitHub username to fetch keys from")
    p_connect.add_argument("--gitlab", help="GitLab username to fetch keys from")
    p_connect.add_argument("--ssh-key", help="SSH public key string (ssh-ed25519 ...)")
    p_connect.add_argument("--age-key", help="age public key string (age1...)")
    p_connect.add_argument("--force", action="store_true", help="Accept changed keys (override fingerprint pinning)")

    # pull
    p_pull = sub.add_parser("pull", help="Decrypt inbound .age files")
    p_pull.add_argument("--dry", action="store_true", help="Dry run")
    p_pull.add_argument("--identity", help="Path to identity file for decryption")

    # list
    p_list = sub.add_parser("list", help="Show connected peers, shared files, encryption state")
    p_list.add_argument("--peer", help="Filter to shares for a specific peer")
    p_list.add_argument("--encrypted-only", action="store_true", help="Show only encrypted shares")
    p_list.add_argument("--json", action="store_true", help="JSON output")

    # init
    p_init = sub.add_parser("init", help="Create manifest from scratch")
    p_init.add_argument("--name", help="Workspace name")
    p_init.add_argument("--user", help="User name")
    p_init.add_argument("--ai-collab", help="Path to ai-collab repo (default: ../ai-collab)")
    p_init.add_argument("--repo", nargs=2, action="append", metavar=("NAME", "PATH"),
                         help="Additional repo (repeatable): --repo iu-shared ../iu-shared")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing")

    args = parser.parse_args()
    commands = {
        "check": cmd_check,
        "push": cmd_push,
        "add": cmd_add,
        "remove": cmd_remove,
        "connect": cmd_connect,
        "pull": cmd_pull,
        "list": cmd_list,
        "init": cmd_init,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
