---
name: collab
description: Shared context collaboration — share knowledge, send messages, sync with collaborators. Use when user says "share this", "send to [person]", "check inbox", "sync collab", "what has [person] shared", "collab setup", "add [person]", or any intent to share context, communicate with collaborators, or manage the shared space.
argument-hint: "setup | share <topic> | sync | inbox | send <person> <msg> | ask <question> | read <person> | decide <topic> | status | brief <person> | contacts | add-collaborator <name>"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Collab — Shared Context Collaboration

## Architecture: Plugin + Data Repos

**This plugin provides the SKILL (agent instructions). The DATA lives in separate shared repos.**

```
┌─────────────────────────────┐
│  claude-plugins (this repo) │    DATA REPOS (one or more)
│  ─────────────────────────  │    ─────────────────────────
│  • SKILL.md (agent brain)   │    ┌────────────────────────────────┐
│  • hooks (dep check)        │    │  ai-collab (GitHub)            │
│  • scripts                  │    │  • tools/collab-sync/ (CLI)    │
│  ─────────────────────────  │    │  • person/outbound/ (shares)   │
│  PUBLIC — anyone can install│    │  • person/inbox/ (messages)    │
│  Contains: zero user data   │    │  • shared/ (joint decisions)   │
└─────────────────────────────┘    └────────────────────────────────┘
                                   ┌────────────────────────────────┐
                                   │  shared-context (GitHub)       │
                                   │  • Private pair sharing        │
                                   │  • E.g. Benjamin ↔ Quintus    │
                                   └────────────────────────────────┘
                                   ┌────────────────────────────────┐
                                   │  iu-shared (GitLab)            │
                                   │  • IU team-wide iu-public      │
                                   │  • IU colleague private shares │
                                   └────────────────────────────────┘

┌──────────────────────────────────┐
│  Your workspace (local only)     │
│  ──────────────────────────────  │
│  • CLAUDE.md                     │
│  • .collab-manifest.yml          │
│  •   repos: ai-collab, ...      │
│  • .collab-keys/ (peer pubkeys)  │
│  • shared-context/inbound/       │
│    (symlinks → all repos)        │
│  • inbox/ai-collab/              │
│  • inbox/shared-context/         │
│  • inbox/iu-shared/              │
│  ──────────────────────────────  │
│  YOUR machine only               │
│  Never pushed anywhere           │
└──────────────────────────────────┘
```

**Not everyone needs all repos.** Typical configurations:
- **Product team** (Benjamin, Quintus): `ai-collab` + `shared-context`
- **IU team member** (Lasse, Natalie): `iu-shared` + `ai-collab` (for the tool)
- **IU team + private pair**: all three

**When a new person installs this plugin and runs `/collab setup`:**
- The plugin tells their Claude agent HOW to collaborate
- Setup detects + clones the repos they should have access to
- Their encrypted files live in `<repo>/<name>/outbound/`
- Their received files appear in `shared-context/inbound/` via symlinks
- Their local workspace (notes, docs, projects) stays 100% local

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
repos:
  ai-collab: ../ai-collab       # GitHub — private collab, tool dev
  iu-shared: ../iu-shared       # GitLab — IU team sharing (optional)

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

**Dependencies (lazy install):** Before running ANY `collab-sync` command, check deps are available. If missing, install on the spot — this avoids SessionStart timeout issues:
```bash
python3 -c "import yaml, pyrage, httpx" 2>/dev/null || pip3 install --user pyyaml pyrage httpx
```

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
   - "add-collaborator"   → Add Collaborator mode
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

The collab system may use multiple repos. Detect and clone all that apply:

```bash
# Check for repos as siblings to workspace
for repo in ai-collab shared-context iu-shared; do
  if [ -d "../$repo/.git" ]; then
    echo "Found $repo at ../$repo"
  else
    echo "$repo not found locally"
  fi
done
```

**For each missing repo:** Ask if the user should have access. Check their profile in any already-found repo (look for collaborator tables in CLAUDE.md). Offer to clone:
```bash
git clone <url> ../<repo-name>
```

**Typical configurations:**
- Benjamin + Quintus (product): `ai-collab` + `shared-context`
- IU team member: `iu-shared` (GitLab) + optionally `ai-collab` (GitHub)
- IU team + private collab: all three

#### 2.5. Install CLI Tools

```bash
# GitHub CLI (for repo invites, key upload)
which gh 2>/dev/null || brew install gh
# GitLab CLI (if IU GitLab repo is configured)
which glab 2>/dev/null || brew install glab
```

After install, check auth:
```bash
gh auth status 2>/dev/null || gh auth login
```

**Fix SSH→HTTPS for GitHub (common issue):**
Claude Code's plugin system and `git clone` may try SSH by default, which fails without SSH keys configured for GitHub. If `gh` is authenticated via HTTPS (the default), configure git to match:
```bash
# Check if SSH works
ssh -T git@github.com 2>&1 | grep -q "successfully" || {
  # SSH doesn't work — set git to use HTTPS for GitHub
  gh auth setup-git
  git config --global url."https://github.com/".insteadOf "git@github.com:"
}
```
This ensures all GitHub git operations (clone, push, pull) use HTTPS with the `gh` token.

If `brew` is not available, show manual install instructions.

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
   - Then upload (see key upload step below)

3. **No SSH key at all:**
   - "No SSH key found. I'll generate one for encrypted collaboration."
   - `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""`
   - Then upload (see key upload step below)

4. **Key upload (CRITICAL — do not skip silently):**
   - Try: `gh ssh-key add ~/.ssh/id_ed25519.pub --title "collab-encryption"`
   - **If `gh` is not installed or upload fails**, show this LOUD warning:
     ```
     ⚠️  YOUR PUBLIC KEY IS NOT UPLOADED YET.

     Others CANNOT send you encrypted files until your ed25519 key
     is on GitHub (or GitLab).

     Upload manually at: https://github.com/settings/ssh/new
     Key to copy: <contents of ~/.ssh/id_ed25519.pub>

     Without this, any file encrypted for you will be unreadable.
     ```
   - Do NOT silently continue. The user must see and acknowledge this.

This is not blocking — plaintext collaboration still works. But flag it for encrypted file support.

#### 6. Create Profile + Folder Scaffold (if new)

Create profiles and folder structure in **each repo the user has access to**. Different repos serve different purposes:

| Repo | Who gets a profile | Purpose |
|------|--------------------|---------|
| `ai-collab` | Product collaborators (Benjamin, Quintus) | Tool dev, private sharing |
| `shared-context` | Private pairs (Benjamin ↔ Quintus) | Person-to-person context |
| `iu-shared` | All IU team members | Team-wide iu-public sharing |

**For each detected repo**, create the user's folder scaffold:
```bash
REPO="../<repo-name>"
mkdir -p $REPO/<name>/outbound/iu-public
mkdir -p $REPO/<name>/outbound/all
mkdir -p $REPO/<name>/inbox/from-general
# Create outbound/README.md and inbox/README.md
```

**Profile** — create in the user's primary repo (ai-collab for product team, iu-shared for IU-only members). Use `templates/profile.md` as guide if available. Fill with interview answers + GitHub/GitLab usernames.

**Cross-create** inbox/outbound folders for existing collaborators in the same repo:
```bash
# For each existing person in REPO
for existing in $(ls $REPO/*/profile.md 2>/dev/null | xargs -I{} dirname {} | xargs -I{} basename {}); do
  [ "$existing" = "<name>" ] && continue
  mkdir -p $REPO/$existing/inbox/from-<name>
  mkdir -p $REPO/<name>/outbound/$existing
  mkdir -p $REPO/<name>/inbox/from-$existing
done
```

#### 7. Initialize Manifest

Create a manifest with all detected repos:
```bash
python3 $AI_COLLAB/tools/collab-sync/sync.py init \
  --name "$(basename $WORKSPACE)" \
  --user "<name>" \
  --ai-collab "<relative-path-to-ai-collab>" \
  --repo shared-context "<relative-path-to-shared-context>" \
  --repo iu-shared "<relative-path-to-iu-shared>"
```

Only include `--repo` flags for repos that exist locally. The `--ai-collab` flag is always included (tool lives there). Example for an IU-only member with no private collab:
```bash
python3 $AI_COLLAB/tools/collab-sync/sync.py init \
  --name "my-workspace" --user "lasse" \
  --ai-collab "../ai-collab" \
  --repo iu-shared "../iu-shared"
```

#### 8. Set Up Symlinks

Create inbound symlinks from **all repos** so the user sees everything in one place:

**IMPORTANT:** Replace `<name>` below with the actual username from Step 4 (e.g., "quintus", "benjamin"). Do NOT leave `<name>` as a literal string — the skip-self check on line 5 will fail and create a useless self-loop symlink.

```bash
WORKSPACE="$(pwd)"
CURRENT_USER="<name>"   # ← REPLACE with actual username from Step 4
mkdir -p shared-context/inbound

# For each configured repo, symlink OTHER collaborators' outbound folders
# SKIP the current user's own outbound (they have the originals)
for REPO_PATH in ../ai-collab ../shared-context ../iu-shared; do
  [ -d "$REPO_PATH" ] || continue
  REPO_NAME=$(basename "$REPO_PATH")

  for person_dir in "$REPO_PATH"/*/; do
    person=$(basename "$person_dir")
    [ "$person" = "$CURRENT_USER" ] && continue  # skip self — no self-loop
    [ "$person" = "shared" ] || [ "$person" = "tools" ] && continue  # skip non-person dirs
    [ -f "$person_dir/profile.md" ] || [ -d "$person_dir/outbound" ] || continue

    # iu-public (team-wide context)
    [ -d "$person_dir/outbound/iu-public" ] && \
      ln -sf "$person_dir/outbound/iu-public" "shared-context/inbound/${person}-iu"

    # Person-specific (private shares for this user)
    [ -d "$person_dir/outbound/$CURRENT_USER" ] && \
      ln -sf "$person_dir/outbound/$CURRENT_USER" "shared-context/inbound/${person}-private"
  done

  # Shared folder (joint decisions, projects)
  [ -d "$REPO_PATH/shared" ] && \
    ln -sf "$REPO_PATH/shared" "shared-context/inbound/${REPO_NAME}-shared"
done

# Inbox symlinks — one per repo that has an inbox for this user
mkdir -p inbox
for REPO_PATH in ../ai-collab ../shared-context ../iu-shared; do
  [ -d "$REPO_PATH/$CURRENT_USER/inbox" ] || continue
  REPO_NAME=$(basename "$REPO_PATH")
  ln -sf "$REPO_PATH/$CURRENT_USER/inbox" "inbox/$REPO_NAME"
done
```

**Add to .gitignore:**
```
shared-context/
inbox/ai-collab/
inbox/shared-context/
inbox/iu-shared/
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

Commit + push in each repo that was modified during setup:
```bash
for REPO_PATH in ../ai-collab ../shared-context ../iu-shared; do
  [ -d "$REPO_PATH/.git" ] || continue
  cd "$REPO_PATH"
  # Only commit if there are staged/new files
  if [ -n "$(git status --porcelain)" ]; then
    git add <name>/
    git commit -m "setup: <name> joined collaboration"
    git push
  fi
  cd -
done
```

#### 12. Done

```
"Collaboration is set up!

Repos configured: [list of repos in manifest]
Profile:          [repo]/<name>/profile.md
Encryption:       [ed25519 ✓ / needs key — see above]
Connected peers:  [list]
Inbound context:  shared-context/inbound/
Inbox:            inbox/[repo-names]/

Try these:
- '/collab status' — see what's shared
- '/collab share <file>' — share something
- '/collab inbox' — check for messages
- '/collab contacts' — see connected peers"
```

---

## Mode: Add Collaborator

**Trigger:** `add-collaborator <name>`, "add [person] to collab", "invite [person]"

### Flow

1. **Ask name** (if not provided as argument)

2. **Ask platform username:**
   - "What's their GitHub username?" (for ai-collab repo)
   - "What's their GitLab username?" (for iu-shared repo, if configured)
   - Need at least one.

3. **Check CLI tools:**
   ```bash
   which gh 2>/dev/null   # for GitHub repos
   which glab 2>/dev/null  # for GitLab repos
   ```
   If missing → offer `brew install gh` / `brew install glab`.

4. **Invite to repo(s):**
   ```bash
   # GitHub
   gh api repos/OWNER/REPO/collaborators/USERNAME -X PUT -f permission=push
   # GitLab (if applicable)
   # Agent looks up project ID and user ID, then invites
   ```

5. **Create folder scaffold** in the appropriate repo(s):
   - IU colleague → create in `iu-shared` (and `ai-collab` if they'll use the tool)
   - Private collaborator → create in `shared-context` (or relevant private repo)
   - Product team → create in `ai-collab`
   ```bash
   for REPO in <relevant-repos>; do
     mkdir -p $REPO/<name>/outbound/iu-public
     mkdir -p $REPO/<name>/outbound/all
     mkdir -p $REPO/<name>/inbox/from-general
     # Cross-create inbox folders for existing collaborators in same repo
     for existing in $(ls $REPO/*/profile.md 2>/dev/null | xargs -I{} dirname {} | xargs -I{} basename {}); do
       [ "$existing" = "<name>" ] && continue
       mkdir -p $REPO/$existing/inbox/from-<name>
     done
   done
   ```

6. **Fetch SSH keys** for encryption:
   ```bash
   python3 $AI_COLLAB/tools/collab-sync/sync.py --workspace $WORKSPACE \
     connect <name> --github <username>
   ```
   If user said "private collaborator" → this step is mandatory.
   Otherwise → optional (iu-public works without encryption).

7. **Create profile** from convention:
   ```markdown
   # <Name>
   **Role:** (to be filled by <name>)
   **Workspace:** (to be set up)
   **AI Tools:** (to be filled)
   **GitHub:** <github-username>
   **GitLab:** <gitlab-username or "(TBD)">
   ```

8. **Update collaborators table** in repo CLAUDE.md

9. **Commit + push** each modified repo:
   ```bash
   # For each repo that was modified
   cd $REPO
   git add <name>/ CLAUDE.md
   git commit -m "setup: <name> joined collaboration"
   git push
   ```

10. **Report:**
    ```
    "Added <name> as collaborator.

    Repos: [list of repos they were added to]
    Encryption: [connected / iu-public only]

    They should:
    1. Install the collab plugin (from claude-plugins)
    2. Run /collab setup in their workspace
    3. They'll automatically see all iu-public shared context.
    4. For private sharing, they need an ed25519 SSH key."
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

   **Repo routing (when multiple repos configured):**
   - `iu-public` → `iu-shared` (GitLab) if available, else `ai-collab`
   - Person-specific → check person's profile for platform. IU colleagues → `iu-shared`, others → `ai-collab`
   - `all` → `ai-collab`
   - Single repo configured → everything goes there (backward compat)

   Pass `--repo <name>` to `collab-sync add` to target the right repo.

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

1. **Read manifest** to discover all configured repos
2. **Pull latest** from each repo: `git pull --rebase` in each configured repo path. Warn on failure, continue with others.
3. **Decrypt inbound:** `collab-sync pull --dry` → if files found → `collab-sync pull` (scans all repos automatically)
4. **Report changes** (new files, decrypted files, messages — grouped by repo)
5. **Update inbound registry** (`.collab-inbound-map.yml` at workspace root, gitignored)

   Scan all files in `shared-context/inbound/*/` (through symlinks). Compare against existing registry entries. For each NEW file not yet in the registry:
   - Read the file (or first 20 lines + any `<!-- tag: ... -->` line)
   - Generate a one-line summary
   - Add entry to the YAML:
     ```yaml
     - source: shared-context/inbound/quintus-private/reorg-notes.md
       from: quintus
       first_seen: 2026-03-02T10:00:00Z
       summary: "Department reorg proposal — PM and engineering restructure"
     ```
   - Create the file if it doesn't exist yet (with `version: 1` header)
   - Skip `.gitkeep` files

   This is registry only — no sorting or mapping to context areas. Just a record of what arrived, from whom, with a summary. The registry enables quick lookups later (see Inbound Context Lookup below).

6. **Symlinks auto-update** (point to repo folders)
7. **Check outbound staleness:** `collab-sync check` → offer re-publish if stale
8. **Check uncommitted changes** in each repo

### Inbound Context Lookup (for the main agent, not sync)

When the main agent needs to check if collaborators have shared something relevant to a topic, it should NOT load all inbound folders into context (doesn't scale with many collaborators). Instead:

1. **Quick check:** Read `.collab-inbound-map.yml` and filter entries by `summary` keywords. One small file covers all inbound content. If matches found → read those files directly.
2. **Deep scan (fallback):** If the registry doesn't exist yet or the topic doesn't match any summary, spawn a **cheap sub-agent** (Haiku) to scan `shared-context/inbound/` directly. Sub-agent reads folder listings and filenames, returns only relevant paths + summaries.

This keeps main context small even with 30+ collaborators sharing files.

---

## Mode: Inbox

**Trigger:** `inbox`, "check messages"

Scan inbox folders across all configured repos. If symlinks are set up, scan `inbox/*/from-*/` (each subfolder is a repo). Otherwise, read manifest and scan `<repo>/<user>/inbox/from-*/` for each repo.

Read YAML frontmatter, present sorted by date, grouped by sender. Enrich with local context.

---

## Mode: Send

**Trigger:** `send <person> <message>`

Compose message with YAML frontmatter (from, date, intent, urgency, tags). Confirm before sending.

**Repo routing for messages:**
- Determine which repo the recipient lives in by checking which repos have a `<recipient>/inbox/` folder
- If recipient exists in multiple repos, prefer: `shared-context` (private pair) > `iu-shared` (IU team) > `ai-collab` (fallback)
- Write to `<repo>/<recipient>/inbox/from-<sender>/YYYY-MM-DD_<slug>.md`

Commit + push to the target repo.

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
