# Claude Plugins — Agent Context Mesh

A Claude Code plugin marketplace for AI-native knowledge sharing and encrypted collaboration.

## Quick Start

```bash
# 1. Add this marketplace
/plugin marketplace add bmeindl/claude-plugins

# 2. Install the cmesh plugin
/plugin install cmesh@bmeindl-plugins

# 3. Run the interactive setup (~5 minutes)
/cmesh setup
```

> **Note:** If step 1 fails with "SSH authentication failed", run this first to use HTTPS:
> ```bash
> git config --global url."https://github.com/".insteadOf "git@github.com:"
> ```

That's it. Setup handles everything: cloning the shared repo, generating SSH keys, installing dependencies, creating your profile, connecting with collaborators.

## Available Plugins

### cmesh (Agent Context Mesh)

**Agent Context Mesh** — share knowledge with your team, encrypted for privacy. Your AI assistant handles encryption, git operations, and routing automatically.

```
/cmesh share strategy-notes.md with Quintus    → encrypted, only Quintus can read
/cmesh share coding-standards.md for the team  → plaintext, visible to all collaborators
/cmesh inbox                                    → check messages from collaborators
/cmesh sync                                     → pull latest + decrypt inbound files
/cmesh status                                   → overview of everything
```

**10 modes:** setup, share, sync, inbox, send, ask, read, decide, status, brief, contacts

**Features:**
- **Intent-based encryption** — say "share with Quintus" and it encrypts automatically
- **age encryption** via SSH ed25519 keys — no GPG, no passwords
- **Key pinning** (TOFU) — warns if a collaborator's keys change unexpectedly
- **Manifest tracking** — checksums, stale detection, auditable share history
- **Privacy-first** — `<!-- private -->` tags, `.collabignore`, explicit confirmation before any share

## Architecture

```
This repo (PUBLIC)              ai-collab repo (PRIVATE)           Your workspace (LOCAL)
────────────────                ──────────────────────             ────────────────────
Plugin code:                    Shared data:                       Your files:
• SKILL.md (agent brain)        • <user>/outbound/ (shares)        • CLAUDE.md
• hooks (dep check)             • <user>/inbox/ (messages)         • .collab-manifest.yml
• scripts                       • shared/ (decisions)              • .collab-keys/ (pubkeys)
Zero user data.                 Encrypted .age files.                (symlinks → ai-collab)
Anyone can install.             Collaborators only.                Never leaves your machine.
```

**The plugin is the brain. The shared repo is the body. Your workspace is yours.**

## Requirements

- **Claude Code** (v1.0.33+ with plugin support)
- **Python 3.9+** (for collab-sync tool)
- **git** (for the shared repo)
- **SSH key** (ed25519 recommended — setup generates one if needed)

Python dependencies (auto-installed during setup):
- `pyyaml` — manifest parsing
- `pyrage` — age encryption (Rust-based, no compilation)
- `httpx` — key fetching from GitHub/GitLab

## For Collaborators Being Invited

If someone invited you to collaborate, here's what happens:

1. You run the 3 commands above
2. `/cmesh setup` asks your name, role, what you're working on
3. It clones the shared repo, creates your profile, generates encryption keys
4. You're done — say `/cmesh inbox` to check for messages

**You don't need to understand encryption, git, or SSH.** The AI handles all of it.

## License

MIT
