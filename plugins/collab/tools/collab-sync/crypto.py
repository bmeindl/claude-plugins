"""Encryption layer: age encryption via pyrage + SSH ed25519 keys.

Provides peer key management (fetch from GitHub/GitLab, local storage)
and encrypt/decrypt operations using age format. pyrage is imported lazily
so the tool stays usable for plaintext-only workflows without it installed.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

COLLAB_KEYS_DIR = ".collab-keys"


# --- Key fetching ---


def fetch_github_keys(username: str) -> list[str]:
    """Fetch SSH public keys from GitHub."""
    return _fetch_keys(f"https://github.com/{username}.keys", f"GitHub user '{username}'")


def fetch_gitlab_keys(username: str) -> list[str]:
    """Fetch SSH public keys from GitLab."""
    return _fetch_keys(f"https://gitlab.com/{username}.keys", f"GitLab user '{username}'")


def _fetch_keys(url: str, label: str) -> list[str]:
    """GET a .keys endpoint, return list of key lines."""
    import httpx

    resp = httpx.get(url, timeout=10, follow_redirects=True)
    if resp.status_code == 404:
        print(f"Warning: No keys found for {label}", file=sys.stderr)
        return []
    resp.raise_for_status()

    keys = [line.strip() for line in resp.text.splitlines() if line.strip()]
    return keys


# --- Key storage ---


def _keys_dir(workspace: Path) -> Path:
    return workspace / COLLAB_KEYS_DIR


def store_peer_keys(workspace: Path, peer: str, keys: list[str]) -> Path:
    """Write peer's public keys to .collab-keys/{peer}.pub."""
    keys_dir = _keys_dir(workspace)
    keys_dir.mkdir(parents=True, exist_ok=True)
    key_file = keys_dir / f"{peer}.pub"
    key_file.write_text("\n".join(keys) + "\n")
    return key_file


def load_peer_keys(workspace: Path, peer: str) -> list[str]:
    """Read peer's public keys from .collab-keys/{peer}.pub."""
    key_file = _keys_dir(workspace) / f"{peer}.pub"
    if not key_file.exists():
        return []
    return [line.strip() for line in key_file.read_text().splitlines() if line.strip()]


def peer_keys_exist(workspace: Path, peer: str) -> bool:
    """Check if we have stored keys for a peer."""
    return (_keys_dir(workspace) / f"{peer}.pub").exists()


# --- Fingerprinting ---


def compute_key_fingerprint(keys: list[str]) -> str:
    """Compute a short fingerprint of a set of public keys.

    Sorts and normalizes keys, then returns first 16 hex chars of SHA256.
    Stable across key reordering.
    """
    normalized = "\n".join(sorted(k.strip() for k in keys if k.strip()))
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def store_fingerprint(workspace: Path, peer: str, fingerprint: str) -> None:
    """Write fingerprint to .collab-keys/{peer}.fingerprint."""
    fp_file = _keys_dir(workspace) / f"{peer}.fingerprint"
    fp_file.write_text(fingerprint + "\n")


def load_fingerprint(workspace: Path, peer: str) -> str | None:
    """Read stored fingerprint for a peer, or None if not stored."""
    fp_file = _keys_dir(workspace) / f"{peer}.fingerprint"
    if not fp_file.exists():
        return None
    return fp_file.read_text().strip()


# --- Recipient building ---


def _build_recipients(keys: list[str]) -> list:
    """Convert key strings to pyrage recipient objects.

    Accepts ssh-ed25519 and age1... keys. Skips ssh-rsa with warning.
    """
    from pyrage import ssh, x25519

    recipients = []
    for key in keys:
        if key.startswith("ssh-ed25519 "):
            recipients.append(ssh.Recipient.from_str(key))
        elif key.startswith("age1"):
            recipients.append(x25519.Recipient.from_str(key))
        elif key.startswith("ssh-rsa "):
            print(f"Warning: Skipping ssh-rsa key (age only supports ed25519): {key[:40]}...", file=sys.stderr)
        elif key.startswith("ssh-"):
            print(f"Warning: Skipping unsupported key type: {key.split()[0]}", file=sys.stderr)
    return recipients


# --- Encrypt / Decrypt ---


def _load_own_public_key() -> str | None:
    """Try to load the sender's own public key for encrypt-to-self.

    Returns key string or None if no usable key found.
    Resolution order: ~/.ssh/id_ed25519.pub, ~/.collab-keys/identity.pub
    """
    ssh_pub = Path.home() / ".ssh" / "id_ed25519.pub"
    if ssh_pub.exists():
        key = ssh_pub.read_text().strip().splitlines()[0].strip()
        if key.startswith("ssh-ed25519 "):
            return key

    age_pub = Path.home() / COLLAB_KEYS_DIR / "identity.pub"
    if age_pub.exists():
        key = age_pub.read_text().strip().splitlines()[0].strip()
        if key.startswith("age1"):
            return key

    return None


def encrypt_for_peer(content: bytes, workspace: Path, peer: str) -> bytes:
    """Encrypt content for a peer using their stored public keys.

    Also includes the sender's own public key as a recipient (encrypt-to-self)
    so the sender can decrypt their own shares. age natively supports multiple
    recipients — same ciphertext, multiple keys.

    Raises ValueError if no usable keys found for the peer.
    """
    import pyrage

    keys = load_peer_keys(workspace, peer)
    if not keys:
        raise ValueError(
            f"No keys found for peer '{peer}'. "
            f"Run: collab-sync connect {peer} --github <username>"
        )

    recipients = _build_recipients(keys)
    if not recipients:
        raise ValueError(
            f"No usable keys for peer '{peer}' (only ssh-ed25519 and age1... keys work). "
            f"Keys found: {[k.split()[0] for k in keys]}"
        )

    # Encrypt-to-self: add sender's own key so they can decrypt their own shares
    own_key = _load_own_public_key()
    if own_key:
        own_recipients = _build_recipients([own_key])
        recipients.extend(own_recipients)
    else:
        print(
            "Warning: No ed25519 SSH key or age identity found. "
            "You won't be able to decrypt your own shares. "
            "Consider: ssh-keygen -t ed25519 or collab-sync init --generate-identity",
            file=sys.stderr,
        )

    return pyrage.encrypt(content, recipients)


def decrypt_with_identity(ciphertext: bytes, identity_path: str | None = None) -> bytes:
    """Decrypt age-encrypted content using local SSH key or age identity.

    Identity resolution order:
    1. Explicit identity_path argument
    2. ~/.ssh/id_ed25519 (SSH ed25519 key)
    3. ~/.collab-keys/identity.txt (native age identity)
    """
    import pyrage
    from pyrage import ssh, x25519

    paths_to_try: list[tuple[str, Path]] = []

    if identity_path:
        paths_to_try.append(("explicit", Path(identity_path)))
    else:
        paths_to_try.append(("ssh-ed25519", Path.home() / ".ssh" / "id_ed25519"))
        paths_to_try.append(("age-identity", Path.home() / COLLAB_KEYS_DIR / "identity.txt"))

    for kind, path in paths_to_try:
        if not path.exists():
            continue
        key_data = path.read_bytes()

        try:
            if kind == "age-identity":
                # Native age identity: AGE-SECRET-KEY-1...
                identity = x25519.Identity.from_str(key_data.decode().strip())
            else:
                # SSH key (ed25519)
                identity = ssh.Identity.from_buffer(key_data)
            return pyrage.decrypt(ciphertext, [identity])
        except Exception as e:
            if identity_path:
                raise
            # Try next identity
            continue

    tried = [str(p) for _, p in paths_to_try]
    raise FileNotFoundError(
        f"No usable identity found. Tried: {', '.join(tried)}. "
        f"Add an ssh-ed25519 key or run: collab-sync connect --generate-identity"
    )


def ensure_own_identity(workspace: Path) -> str:
    """Generate a native age keypair if no ed25519 SSH key exists.

    Returns the public key string (age1...).
    """
    from pyrage import x25519

    ssh_key = Path.home() / ".ssh" / "id_ed25519"
    if ssh_key.exists():
        # Read and return the public key
        pub_key = Path.home() / ".ssh" / "id_ed25519.pub"
        if pub_key.exists():
            return pub_key.read_text().strip()
        return "(ssh-ed25519 key exists but .pub not found)"

    # Generate native age identity
    keys_dir = _keys_dir(workspace)
    keys_dir.mkdir(parents=True, exist_ok=True)
    identity_file = keys_dir / "identity.txt"

    if identity_file.exists():
        # Read existing identity and return public key
        identity = x25519.Identity.from_str(identity_file.read_text().strip())
        return str(identity.to_public())

    identity = x25519.Identity.generate()
    identity_file.write_text(str(identity) + "\n")
    identity_file.chmod(0o600)

    pub_key = str(identity.to_public())
    # Also save public key for sharing
    pub_file = keys_dir / "identity.pub"
    pub_file.write_text(pub_key + "\n")

    print(f"Generated age identity: {identity_file}")
    print(f"Public key: {pub_key}")
    print("Share this public key with collaborators so they can encrypt files for you.")
    return pub_key
