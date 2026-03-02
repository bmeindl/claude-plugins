---
name: collab
description: Shared context collaboration — share knowledge, send messages, sync with collaborators. Use when user says "share this", "send to [person]", "check inbox", "sync collab", "what has [person] shared", "collab setup", or any intent to share context, communicate with collaborators, or manage the shared space.
argument-hint: "setup | share <topic> | sync | inbox | send <person> <msg> | ask <question> | read <person> | decide <topic> | status | brief <person> | contacts"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Collab — Shared Context Collaboration

## Architecture: Two Repos, One Workflow

**This plugin provides the SKILL (agent instructions). The DATA lives in a separate shared repo.**

```
┌─────────────────────────────┐    ┌──────────────────────────────────┐
│  claude-plugins (this repo) │    │  ai-collab (shared data repo)    │
│  ─────────────────────────  │    │  ──────────────────────────────  │
│  • SKILL.md (agent brain)   │    │  • tools/collab-sync/ (CLI)      │
│  • hooks (dep check)        │    │  • benjamin/outbound/ (shares)   │
│  • scripts                  │    │  • benjamin/inbox/ (messages)    │
│  ─────────────────────────  │    │  • quintus/outbound/ (shares)    │
│  PUBLIC — anyone can install│    │  • quintus/inbox/ (messages)     │
│  Contains: zero user data   │    │  • shared/ (joint decisions)     │
└─────────────────────────────┘    │  ──────────────────────────────  │
                                   │  PRIVATE — collaborators only    │
                                   │  Contains: all shared files      │
                                   │  Encrypted .age files per-person │
                                   └──────────────────────────────────┘

┌──────────────────────────────────┐
│  Your workspace (local only)     │
│  ──────────────────────────────  │
│  • CLAUDE.md                     │
│  • .collab-manifest.yml          │
│  • .collab-keys/ (peer pubkeys)  │
│  • shared-context/inbound/       │
│    (symlinks → ai-collab)        │
│  • inbox/ai-collab/              │
│    (symlink → ai-collab)         │
│  ──────────────────────────────  │
│  YOUR machine only               │
│  Never pushed anywhere           │
└──────────────────────────────────┘
```

**When Quintus installs this plugin and runs `/collab setup`:**
- The plugin tells his Claude agent HOW to collaborate
- Setup clones ai-collab to his machine (the shared data repo)
- His encrypted files live in `ai-collab/quintus/outbound/`
- His received files appear in `shared-context/inbound/` via symlinks
- His local workspace (notes, docs, projects) stays 100% local

**Encryption flow:**
- Benjamin shares with Quintus → encrypted with Quintus' public key → `ai-collab/benjamin/outbound/quintus/file.md.age`
- Quintus syncs → decrypts with his private SSH key → reads as plaintext locally
- Anyone with repo access sees only binary `.age` blobs in person-specific folders
- Team-wide shares (`outbound/iu-public/`) stay plaintext — visible to all collaborators

## What This Skill Does

One skill for all collaboration:
- **Setup** — Clone shared repo, create profile, generate keys, configure everything
- **Share** — Publish local context to the shared space with auto-encryption
- **Sync** — Pull latest + decrypt inbound + check for stale shares
- **Inbox** — Check messages from collaborators
- **Send** — Write a message to a collaborator's inbox
- **Ask** — Search all shared context (inbound + shared)
- **Read** — Read a specific collaborator's shared context
- **Decide** — Log a decision in the shared decision log
- **Status** — Overview of shared context, encryption state, manifest health
- **Brief** — Generate a briefing from a collaborator's shared context
- **Contacts** — View connected peers, encryption status, fingerprints

## The Manifest — `.collab-manifest.yml`

The manifest lives at the workspace root (tracked in git) and records what's shared from this workspace, to which repos, with checksums and timestamps.

**Schema:**
```yaml
version: 1
workspace: ground-control
user: benjamin
ai_collab_path: ../ai-collab

shares:
  - source: path/to/local/file.md       # relative to workspace root
    status: active                        # active | source_missing | paused
    targets:
      - repo: ai-collab                  # target repo name
        dest: benjamin/outbound/iu-public/file.md  # path in target
        visibility: iu-public             # iu-public | <person> | all
        last_synced: 2026-03-01T14:00:00Z
        source_checksum: <sha256>         # for stale detection
        tag: "~150 char description"
        encrypt_for: ""                   # empty = plaintext, person name = age-encrypted
```

**Deterministic sync tool:** `ai-collab/tools/collab-sync/sync.py` handles all file operations:
```bash
collab-sync check              # Report stale/missing shares (read-only)
collab-sync check --summary    # Short summary for status display
collab-sync push               # Copy changed files to target, commit, push
collab-sync push --dry         # Show what would happen
collab-sync add <file>         # Add a file to manifest
collab-sync remove <source>    # Remove a share entry
collab-sync connect <name> --github/--gitlab <username>  # Fetch + store peer encryption keys
collab-sync pull [--dry]       # Decrypt inbound .age files
collab-sync list [--peer <name>] [--json]  # Show connected peers + shared files
```

**How to run it:** `python3 $AI_COLLAB/tools/collab-sync/sync.py --workspace $WORKSPACE <command>`
Where `$AI_COLLAB` = the ai-collab repo path, `$WORKSPACE` = user's workspace root.

**Encryption model:** Person-specific shares are automatically age-encrypted. Team-wide and public shares stay plaintext.

```
outbound/<person>/  → auto-encrypted (requires connect first)
outbound/iu-public/ → plaintext
outbound/all/       → plaintext
```

**Division of labor:**
| Responsibility | Handled by |
|---------------|-----------|
| What to share, with whom, what tag | LLM agent (this skill) |
| Copy file, check privacy, encrypt, commit, push | `collab-sync` tool (deterministic) |
| What's stale, what's missing | `collab-sync check` (deterministic) |
| Should we re-publish stale files? | LLM agent (this skill, presents results) |

**Safety (enforced by collab-sync, NOT by LLM):**
- `<!-- private -->` in first line → hard skip, cannot be overridden
- `.collabignore` files exclude entire folders/patterns
- Source file missing → mark `status: source_missing`, warn, never delete from target
- Target repo dirty → refuse push
- Missing encryption keys → fail before touching any files

## Prerequisites

**Shared repo:** The ai-collab repo must be cloned locally. The setup flow handles this.

**Detect ai-collab location:**
```bash
# Check common locations relative to workspace
ls ../ai-collab/CLAUDE.md 2>/dev/null        # sibling
ls ../../ai-collab/CLAUDE.md 2>/dev/null      # parent's sibling
```

If not found → setup flow offers to clone it.

**Detect current user:** Read the workspace CLAUDE.md or `ai-collab/CLAUDE.md` collaborators table. Confirm if ambiguous.

## Smart Default: Detect User State

**On invocation, check state before asking what to do:**

```
1. Are symlinks configured? (check for shared-context/ or inbox/ai-collab/)
   - No → Suggest setup
   - Yes → Existing user → Show menu

2. If arguments provided, route directly:
   - "setup"              → Setup mode
   - "share <topic>"      → Share mode
   - "sync"               → Sync mode
   - "inbox"              → Inbox mode
   - "send <person> <msg>"→ Send mode
   - "ask <question>"     → Ask mode
   - "read <person>"      → Read mode
   - "decide <topic>"     → Decide mode
   - "status"             → Status mode
   - "brief <person>"     → Brief mode
   - "contacts"           → Contacts mode
   - Natural language      → Infer intent
```

---

## Mode: Setup

**Trigger:** First invocation (no symlinks) or explicit `setup`

**Time target:** ~5 minutes for full setup.

### Flow

#### 1. Welcome

```
"I'll set up shared context collaboration so you can share knowledge
and communicate with your collaborators. Takes about 5 minutes.

First, let me check your environment."
```

#### 2. Detect Environment + Auto-Clone

```bash
# Find ai-collab repo
AI_COLLAB=""
for path in ../ai-collab ../../ai-collab ~/Documents/ai-collab; do
  if [ -f "$path/CLAUDE.md" ]; then
    AI_COLLAB="$(cd "$path" && pwd)"
    break
  fi
done
```

**If not found — offer to clone:**
```
"I can't find the shared repo (ai-collab). I'll clone it for you.

Where is it hosted?
1. GitHub (e.g., github.com/org/ai-collab)
2. GitLab (e.g., gitlab.com/org/ai-collab)
3. Other git URL"
```

Then: `git clone <url> ../ai-collab`

#### 3. Install Dependencies

```bash
# Check and install Python packages
python3 -c "import yaml, pyrage, httpx" 2>/dev/null || {
  echo "Installing collaboration dependencies..."
  pip3 install pyyaml pyrage httpx
}
```

If pip fails → "Python packages couldn't be installed automatically. Please run: `pip3 install pyyaml pyrage httpx`"

#### 4. Identify User

Ask: "What's your name?" (match against ai-collab collaborators table)

If new collaborator:
```
"Welcome! I'll create your space in the shared repo.
A few quick questions:"
```

Ask:
1. "What's your role?"
2. "What are you mainly working on right now?"
3. "What AI tools do you use?" (Claude Code, Cursor, Windsurf, etc.)

#### 5. Check Encryption Key Compatibility

Check if the user can send AND receive encrypted shares:

1. **Check `~/.ssh/id_ed25519`:**
   - If exists → "Your SSH key supports encryption. You can send and receive encrypted shares."
   - If not found, continue to step 2.

2. **Check `~/.ssh/id_rsa`:**
   - If exists → "Your SSH key is RSA. You CAN encrypt for others, but you CAN'T receive encrypted files."
   - Offer: "I'll generate an ed25519 key alongside your RSA key. This won't affect your existing setup."
   - On confirm: `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""`
   - Then offer to upload: `gh ssh-key add ~/.ssh/id_ed25519.pub --title "collab-encryption"` (if gh CLI available)

3. **No SSH key at all:**
   - "No SSH key found. I'll generate one for encrypted collaboration."
   - `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""`
   - Offer GitHub upload via `gh ssh-key add`

This is not blocking — plaintext collaboration still works. But flag it for encrypted file support.

#### 6. Create Profile (if new)

Create `ai-collab/<name>/profile.md` using `templates/profile.md` as guide.
Fill with answers from the interview.

Also create folder structure:
```bash
mkdir -p ai-collab/<name>/outbound/iu-public
mkdir -p ai-collab/<name>/outbound/all
mkdir -p ai-collab/<name>/inbox/from-general
# Create outbound/README.md and inbox/README.md
```

Create per-person inbox folders for each existing collaborator:
```bash
# For each existing person, create from-<name> in their inbox
mkdir -p ai-collab/<existing>/inbox/from-<new-name>
# And create outbound/<existing> for person-specific sharing
mkdir -p ai-collab/<name>/outbound/<existing>
```

#### 7. Initialize Manifest

```bash
python3 $AI_COLLAB/tools/collab-sync/sync.py init \
  --name "$(basename $WORKSPACE)" \
  --user "<name>" \
  --ai-collab "<relative-path-to-ai-collab>"
```

#### 8. Set Up Symlinks

Determine the workspace structure:

**For any workspace:**
```bash
WORKSPACE="$(pwd)"

# Create inbound directory
mkdir -p shared-context/inbound

# For each collaborator, symlink their outbound folders
# iu-public (team-wide) + person-specific (for this user)
for person in $(ls $AI_COLLAB/*/profile.md 2>/dev/null | xargs -I{} dirname {} | xargs -I{} basename {}); do
  [ "$person" = "<name>" ] && continue  # skip self
  [ -d "$AI_COLLAB/$person/outbound/iu-public" ] && \
    ln -sf "$AI_COLLAB/$person/outbound/iu-public" "shared-context/inbound/${person}-iu"
  [ -d "$AI_COLLAB/$person/outbound/<name>" ] && \
    ln -sf "$AI_COLLAB/$person/outbound/<name>" "shared-context/inbound/${person}-private"
done
[ -d "$AI_COLLAB/shared" ] && \
  ln -sf "$AI_COLLAB/shared" "shared-context/inbound/shared"

# Inbox symlink
mkdir -p inbox
ln -sf "$AI_COLLAB/<name>/inbox" inbox/ai-collab
```

**Add to .gitignore:**
```
shared-context/
inbox/ai-collab/
.collab-keys/
```

#### 9. Connect with Existing Collaborators

For each existing person in ai-collab, auto-connect if they have a GitHub profile linked:
```bash
# Read their profile for github username, then connect
python3 $AI_COLLAB/tools/collab-sync/sync.py connect <person> --github <username>
```

#### 10. Update Local CLAUDE.md

Add a "Shared Context" section adapted to the actual symlink paths and collaborators.

#### 11. Commit + Push Setup

```bash
cd $AI_COLLAB
git add <name>/
git commit -m "setup: <name> joined collaboration"
git push
```

#### 12. Done

```
"Collaboration is set up!

Your space:       ai-collab/<name>/
Profile:          ai-collab/<name>/profile.md
Encryption:       [ed25519 ✓ / needs key — see above]
Connected peers:  [list]
Inbound context:  shared-context/inbound/
Inbox:            inbox/ai-collab/

Try these:
- '/collab status' — see what's shared
- '/collab share <file>' — share something
- '/collab inbox' — check for messages
- '/collab contacts' — see connected peers"
```

---

## Mode: Share

**Trigger:** `share <topic>`, or "share this with [person/group]"

### The Publishing Rule

**ALWAYS confirm before sharing.** Never auto-publish. Show:
1. What will be shared (file or content summary)
2. Where it will go (which outbound folder)
3. Who will see it (visibility + encryption)

### Flow

1. **Identify content to share**
   - If user specifies a file → read it
   - If user describes content → find it in the workspace (search context/, inbox/, etc.)
   - If ambiguous → ask: "Which file or content do you want to share?"

2. **Determine visibility**
   - If user says "with Quintus" → `outbound/quintus/`
   - If user says "for IU" or "for the team" → `outbound/iu-public/`
   - If user says "for everyone" or "public" → `outbound/all/`
   - If not specified → ask: "Who should see this?"

   Visibility options:
   ```
   - [person name] — only that person (encrypted)
   - [person1, person2] — those specific people (encrypted copy in each)
   - iu-public — anyone at IU (all repo collaborators, plaintext)
   - everyone — completely public (plaintext)
   ```

   **Encryption (automatic for person-specific shares):**
   When visibility is a person name (not `iu-public`, not `all`):
   1. Check if `.collab-keys/{person}.pub` exists in the workspace
   2. **If missing:** Ask: "To encrypt for {person}, I need their SSH public keys. What's their GitHub (or GitLab) username?" → run `collab-sync connect {person} --github {username}`
   3. **If found:** Proceed automatically — encryption is transparent
   4. Add `--encrypt-for {person}` to the `collab-sync add` command
   5. The tool auto-appends `.age` to the dest path

   The user never types `--encrypt-for`. They say "share this with Quintus" → you detect person-specific → check for keys → encrypt automatically.

3. **Generate tag** (auto-generated from content if not provided)
   - Read the content, produce a ~150 char description
   - Show it to the user for confirmation

4. **Confirm**
   ```
   "I'll share this to ai-collab/<user>/outbound/<visibility>/<filename>.md
   Visible to: [who]
   Encryption: [encrypted for <person> / plaintext]
   Tag: [generated tag]

   Confirm? [Yes/No]"
   ```

5. **Write the shared file**

   ```markdown
   ---
   shared_from: <original-path-relative-to-workspace>
   shared_at: <ISO date>
   ---
   <!-- tag: [the tag] -->

   [content from the original file]
   ```

6. **Update outbound/README.md**

7. **Update manifest + commit + push**

   ```bash
   # For person-specific (encrypted):
   python3 $AI_COLLAB/tools/collab-sync/sync.py \
     --workspace $WORKSPACE add "$SOURCE_REL" \
     --dest "<user>/outbound/<person>/<filename>.md" \
     --visibility "<person>" --encrypt-for "<person>" --tag "<tag>"

   # For team/public (plaintext):
   python3 $AI_COLLAB/tools/collab-sync/sync.py \
     --workspace $WORKSPACE add "$SOURCE_REL" \
     --dest "<user>/outbound/<visibility>/<filename>.md" \
     --visibility "<visibility>" --tag "<tag>"
   ```

   Then: `collab-sync push` (handles git add + commit + push for specific files only)

8. **Optionally annotate local file** with `<!-- shared -->` tag

### Multi-Person Visibility

When sharing with specific people (e.g., "share with Quintus and Lasse"):
- Copy the file to `outbound/quintus/` AND `outbound/lasse/`
- Both get encrypted independently (each with their own keys)

---

## Mode: Sync

**Trigger:** `sync`, "pull shared context", "update collab"

### Flow

1. **Find ai-collab repo** (from manifest or detect)
2. **Pull latest:** `git pull --rebase` in ai-collab
3. **Decrypt inbound:** `collab-sync pull --dry` → if files found → `collab-sync pull`
4. **Report changes** (new files, decrypted files, messages)
5. **Symlinks auto-update** (point to ai-collab)
6. **Check outbound staleness:** `collab-sync check` → offer re-publish if stale
7. **Check uncommitted changes** in ai-collab

---

## Mode: Inbox

**Trigger:** `inbox`, "check messages"

Scan `ai-collab/<user>/inbox/from-*/`, read YAML frontmatter, present sorted by date. Enrich with local context.

---

## Mode: Send

**Trigger:** `send <person> <message>`

Compose message with YAML frontmatter (from, date, intent, urgency, tags). Confirm before sending. Write to `ai-collab/<recipient>/inbox/from-<sender>/`. Commit + push.

---

## Mode: Ask

**Trigger:** `ask <question>`

Search shared context (shared/, inbound/, profiles). Summarize findings, cite sources.

---

## Mode: Read

**Trigger:** `read <person>`

Read their outbound/README.md, present overview of what they've shared (iu-public + private for you).

---

## Mode: Decide

**Trigger:** `decide <topic>`

Draft decision record, write to `ai-collab/shared/decisions/`. Commit + push.

---

## Mode: Status

**Trigger:** `status`

Show: setup state, inbound context, outbound shares, encryption state (identity, peers, encrypted vs plaintext counts, pending inbound), manifest health, inbox count, profile status. Use `collab-sync list --json` for encryption data.

---

## Mode: Brief

**Trigger:** `brief <person>`

Read profile + shared content, synthesize a briefing. Read-only.

---

## Mode: Contacts

**Trigger:** `contacts`, "who am I connected with?"

### Flow

```bash
python3 $AI_COLLAB/tools/collab-sync/sync.py --workspace $WORKSPACE list --json
```

**Present as contact book:**
```
Your Contacts
─────────────
  quintus      Quintus Stierstorfer    ed25519 ✓    fp: a3f8...2b1c
  lasse        Lasse (pending setup)   not connected

Add a contact: /collab connect <name> --github <username>
```

For each contact, also show: last shared file, last message, encryption status.

---

## Core Behaviors (Always Active)

### Privacy First
- **Default to private.** Never share without explicit confirmation.
- **Enrich, don't dump.** Add context to messages — don't attach raw files.

### Index Updates (Write-Time)
Every write to ai-collab updates the relevant README.md in the same action.

### Git Safety
- Always pull before push
- Never force-push
- Commit messages: `share:`, `msg:`, `decision:`, `profile:`, `setup:`
- One operation = one commit
- Stage only specific files (never `git add -A`)

### Symlink Awareness
Local paths (e.g., `shared-context/inbound/quintus-iu/`) are symlinks to ai-collab. Read via local path, write directly in ai-collab.

---

## Reference Files

| File | Purpose |
|------|---------|
| `ai-collab/tools/collab-sync/` | Deterministic sync tool (Python CLI) |
| `ai-collab/templates/profile.md` | Collaborator profile template |
| `ai-collab/templates/decision.md` | Decision record template |
| `ai-collab/CLAUDE.md` | How any agent should use the shared repo |
