---
name: cmesh
description: Agent Context Mesh — share knowledge, send messages, sync with collaborators. Use when user says "share this", "send to [person]", "check inbox", "sync cmesh", "what has [person] shared", "cmesh setup", or any intent to share context, communicate with collaborators, or manage the shared space.
argument-hint: "setup | share <topic> | sync | inbox | send <person> <msg> | ask <question> | read <person> | decide <topic> | status | brief <person>"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Agent Context Mesh — Shared Context Collaboration

## What This Skill Does

One skill for all collaboration:
- **Setup** — Create profile, set up symlinks, configure CLAUDE.md integration
- **Share** — Publish local context to the shared space with visibility controls
- **Sync** — Pull latest + check for stale local shares via manifest
- **Inbox** — Check messages from collaborators
- **Send** — Write a message to a collaborator
- **Ask** — Search all shared context (inbound from collaborators)
- **Read** — Read a specific collaborator's shared context
- **Decide** — Log a decision record
- **Status** — Overview of shared context, inbox count, sync state, manifest health
- **Brief** — Generate a briefing from a collaborator's shared context

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
        dest: benjamin/quintus/file.md    # path in target (<sender>/<recipient>/)
        visibility: quintus               # <person> (ai-collab is always bilateral)
        last_synced: 2026-03-01T14:00:00Z
        source_checksum: <sha256>         # for stale detection
        tag: "~150 char description"
        encrypt_for: quintus              # person name = age-encrypted (always for ai-collab)
      - repo: syntea-shared-context       # IU GitLab team knowledge (nested clone at ai-collab/team/)
        dest: lasting/file.md             # path in target (lasting/ or operational/)
        visibility: iu-public             # team-wide sharing
        last_synced: 2026-03-01T14:00:00Z
        source_checksum: <sha256>
        tag: "~150 char description"
        encrypt_for: ""                   # team shares are plaintext
```

**Deterministic sync tool:** `tools/collab-sync/sync.py` handles all file operations (found via `$COLLAB_TOOL` discovery — see Mode: Setup):
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

**Encryption model:** All bilateral shares are person-to-person and automatically age-encrypted. Team-wide knowledge goes to `ai-collab/team/` (a nested IU GitLab clone, plaintext). The agent decides routing; `collab-sync` handles encryption transparently.

```
ai-collab/<sender>/<person>/  → auto-encrypted (requires connect first)
ai-collab/team/               → plaintext (IU team knowledge, nested GitLab clone)
```

**Division of labor:**
| Responsibility | Handled by |
|---------------|-----------|
| What to share, with whom, what tag | LLM agent (this skill) |
| Copy file, check privacy, commit, push | `collab-sync` tool (deterministic) |
| What's stale, what's missing | `collab-sync check` (deterministic) |
| Should we re-publish stale files? | LLM agent (this skill, presents results) |

**Safety (enforced by collab-sync, NOT by LLM):**
- `<!-- private -->` in first line → hard skip, cannot be overridden
- `.collabignore` files exclude entire folders/patterns
- Source file missing → mark `status: source_missing`, warn, never delete from target

**How to make a file permanently private:** Add `<!-- private -->` as the very FIRST line of the file. The sync tool will refuse to share it regardless of what you or the agent ask. This is enforced in code (`safety.py`), not by the LLM. Use this for personal notes, credentials, or anything that should never leave your workspace.
- Target repo dirty → refuse push

## Prerequisites

**Shared repo:** `ai-collab/` must be cloned as a sibling to your workspace (e.g., `~/Documents/ai-collab/`).

**Team knowledge (optional):** If the user shares IU team knowledge, `ai-collab/team/` should contain a clone of `syntea.shared.context` from IU GitLab. This is a nested clone (separate `.git`, gitignored by parent). Setup handles this automatically.

**Detect ai-collab location:**
```bash
# Check common locations relative to workspace
ls ../ai-collab/CLAUDE.md 2>/dev/null        # sibling
ls ../../ai-collab/CLAUDE.md 2>/dev/null      # parent's sibling
```

If not found, ask the user for the path.

**Detect current user:** Read the workspace CLAUDE.md or `ai-collab/CLAUDE.md` collaborators table to determine who the current user is. Confirm with the user if ambiguous.

## Smart Default: Detect User State

**On invocation, check state before asking what to do:**

```
1. Are symlinks configured? (check for shared-context/inbound/)
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
   - Natural language      → Infer intent
```

**For existing users with no arguments:**
```
"I can help you collaborate:
- **Share** — Publish context for others to see
- **Inbox** — Check messages from collaborators
- **Send** — Message a collaborator
- **Sync** — Pull latest shared context
- **Ask** — Search shared knowledge
- **Status** — Overview of collaboration state

What do you need?"
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

#### 2. Detect Environment

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

If not found: "I can't find the ai-collab data repo. Please clone it as a sibling to your workspace:
`git clone https://github.com/<org>/ai-collab.git` (next to your workspace folder, NOT inside it)."

```bash
# Find cmesh tool (sync CLI)
# Priority: claude-plugins sibling → workspace mount → plugin-relative → plugin cache
COLLAB_TOOL=""
for path in ../claude-plugins/plugins/cmesh \
            "$WORKSPACE/personal/projects/claude-plugins/plugins/cmesh" \
            "$(dirname "$SKILL_PATH")/../.." \
            ~/.claude/plugins/*/cmesh \
            ~/.claude/plugins/cache/cmesh; do
  if [ -d "$path/tools/collab-sync" ]; then
    COLLAB_TOOL="$(cd "$path" && pwd)"
    break
  fi
done
```

If not found, offer to clone it:
"I can't find collab-sync. Let me clone the plugins repo as a sibling to your workspace."
```bash
cd "$(dirname "$WORKSPACE")"
git clone https://github.com/bmeindl/claude-plugins.git
COLLAB_TOOL="$(cd ../claude-plugins/plugins/cmesh && pwd)"
```

#### 3. Identify User

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

#### 4. Check Encryption Key Compatibility

Check if the user can send AND receive encrypted shares:

1. **Check `~/.ssh/id_ed25519`:**
   - If exists → "Your SSH key supports encryption. You can send and receive encrypted shares."
   - If not found, continue to step 2.

2. **Check `~/.ssh/id_rsa`:**
   - If exists → "Your SSH key is RSA. You CAN encrypt for others, but you CAN'T receive encrypted files yourself."
   - Offer: "Would you like to generate an ed25519 key? Run: `ssh-keygen -t ed25519` (keeps your RSA key, adds a second key)"
   - Alternative: "Or I can generate a native age identity: `collab-sync init --generate-identity`"

3. **No SSH key at all:**
   - "No SSH key found. To receive encrypted shares, you need one."
   - Offer: `ssh-keygen -t ed25519` or `collab-sync init --generate-identity`

This is not blocking — users can still collaborate with plaintext shares. But flag it so they know encrypted files won't work until resolved.

#### 5. Create Profile (if new)

Create `ai-collab/<name>/profile.md` using `templates/profile.md` as guide.
Fill with answers from the interview.

Also create folder structure:
```bash
# Create a subfolder for each existing collaborator
for collab in $(ls -d ai-collab/*/profile.md 2>/dev/null | xargs -I{} dirname {} | xargs -n1 basename); do
  mkdir -p "ai-collab/<name>/$collab"
done
# Also create reverse: existing collaborators get a subfolder for the new person
for collab in $(ls -d ai-collab/*/profile.md 2>/dev/null | xargs -I{} dirname {} | xargs -n1 basename); do
  mkdir -p "ai-collab/$collab/<name>"
done
```

#### 6. Set Up Symlinks

Determine the workspace structure. The skill needs to know:
- Where PM/work context lives (for inbound shared context)

**For a ground-control-style workspace:**
```bash
WORKSPACE="$(pwd)"  # e.g., /Users/name/Documents/ground-control

# INBOUND: One symlink per collaborator pointing to their folder for you
mkdir -p syntea-pm/shared-context/inbound

# For each collaborator, symlink their folder addressed to you
# Example: Quintus → link quintus/benjamin (what Quintus shares with you)
ln -s "$AI_COLLAB/quintus/benjamin" syntea-pm/shared-context/inbound/quintus-private
```

No inbox symlink needed — `/cmesh inbox` scans `ai-collab/*/<you>/` directly.

**Important: inbound files are read-only.** Never move, rename, or delete files in a collaborator's folder. Those are their copies, published from their workspace. The author controls their lifecycle.

**For a minimal/new workspace:**
```bash
mkdir -p shared-context/inbound
# Same symlink pattern but at workspace root
```

**Add to .gitignore** (in the local workspace):
```
# Shared context (symlinks to ai-collab)
syntea-pm/shared-context/
# Or for minimal workspace:
shared-context/
```

#### 7. Update Local CLAUDE.md

Add a "Shared Context (AI Collab)" section to the workspace's CLAUDE.md:

```markdown
## Shared Context (AI Collab)

Shared context from collaborators appears as local folders via symlinks.
No special handling needed — just read them like any other context.

**Inbound (PM workspace):** `syntea-pm/shared-context/inbound/` contains:
- `quintus-private/` — Quintus' context shared specifically with Benjamin

**On startup for PM work:** Skim inbound folders for recently shared context.

**Commands:**
- `/cmesh sync` — Pull latest from ai-collab (symlinks auto-update)
- `/cmesh share` — Publish local context to the shared space
- `/cmesh inbox` — Check messages from collaborators (scans ai-collab/*/<you>/)
- `/cmesh send <person> <msg>` — Send a message
- `/cmesh status` — Overview of collaboration state
```

Adapt the section to match the actual symlink paths and collaborators.

#### 8. Done

```
"Collaboration is set up:

- Profile created at ai-collab/<name>/profile.md
- Symlinks: shared context from [collaborators] appears locally
- CLAUDE.md updated with shared context routing

Try these:
- '/cmesh status' — see what's shared
- '/cmesh share <topic>' — share something
- '/cmesh inbox' — check for messages
- '/cmesh sync' — pull latest context"
```

---

## Mode: Share

**Trigger:** `share <topic>`, or "share this with [person/group]"

### The Publishing Rule

**ALWAYS confirm before sharing.** Never auto-publish. Show:
1. What will be shared (file or content summary)
2. Where it will go (which target repo and folder)
3. Who will see it (visibility)

### Flow

1. **Identify content to share**
   - If user specifies a file → read it
   - If user describes content → find it in the workspace (search context/, inbox/, etc.)
   - If ambiguous → ask: "Which file or content do you want to share?"

2. **Determine routing**

   Two targets exist — route based on audience:
   - If user says "with Quintus" → ai-collab: `<sender>/quintus/`
   - If user says "with [person]" → ai-collab: `<sender>/<person>/`
   - If user says "for IU" or "for the team" → `ai-collab/team/` (nested IU GitLab clone, via manifest)
   - If not specified → ask: "Who should see this? A specific person, or the whole team?"

   Routing options:
   ```
   - [person name]         → ai-collab/<sender>/<person>/ (encrypted)
   - [person1, person2]    → ai-collab/<sender>/<person>/ for each (encrypted copy)
   - iu/team               → ai-collab/team/ (plaintext, nested IU GitLab clone)
   ```

   **Bilateral shares are always person-specific.** No "public" or "all" visibility in the bilateral folders — everything there is between specific people. Team-wide knowledge goes to `ai-collab/team/` (which is a separate IU GitLab repo, nested inside ai-collab and gitignored by the parent).

   **Encryption (automatic for ai-collab shares):**
   All ai-collab shares are person-specific and auto-encrypted:
   1. Check if `.collab-keys/{person}.pub` exists in the workspace
   2. **If missing:** Ask: "To encrypt for {person}, I need their SSH public keys. What's their GitHub (or GitLab) username?" → run `collab-sync connect {person} --github {username}`
   3. **If found:** Proceed automatically — encryption is transparent
   4. Add `--encrypt-for {person}` to the `collab-sync add` command
   5. The tool auto-appends `.age` to the dest path and handles encryption

   The user never types `--encrypt-for`. They say "share this with Quintus" → you detect person-specific routing → check for keys → encrypt automatically.

3. **Generate tag** (auto-generated from content if not provided)
   - Read the content, produce a ~150 char description
   - Show it to the user for confirmation

4. **Confirm**
   ```
   "I'll share this to ai-collab/<sender>/<recipient>/<filename>.md
   Visible to: [who]
   Encryption: [encrypted for <person>]
   Tag: [generated tag]

   Confirm? [Yes/No]"
   ```

   For team shares (IU GitLab via ai-collab/team/):
   ```
   "I'll share this to ai-collab/team/ (IU GitLab)
   Visible to: IU team
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

6. **Update manifest + commit + push**

   If `.collab-manifest.yml` exists in the workspace:
   ```bash
   # Add to manifest (computes checksum, records entry)
   # For person-specific (ai-collab, encrypted):
   python3 $COLLAB_TOOL/tools/collab-sync/sync.py \
     --workspace $WORKSPACE \
     add "$SOURCE_REL" \
     --dest "<sender>/<recipient>/<filename>.md" \
     --visibility "<recipient>" \
     --encrypt-for "<recipient>" \
     --tag "<the tag>"

   # For team knowledge (ai-collab/team/, plaintext, pushed to IU GitLab):
   python3 $COLLAB_TOOL/tools/collab-sync/sync.py \
     --workspace $WORKSPACE \
     add "$SOURCE_REL" \
     --dest "lasting/<filename>.md" \
     --visibility "iu-public" \
     --tag "<the tag>"
   ```

   Then commit and push:
   ```bash
   # For bilateral shares:
   cd $AI_COLLAB
   git add <sender>/<recipient>/
   git commit -m "share: <filename> → <recipient> — <sender>"
   git push

   # For team shares (separate repo inside ai-collab/team/):
   cd $AI_COLLAB/team
   git add .
   git commit -m "share: <filename> — team knowledge"
   git push
   ```

   If no manifest exists, skip the `collab-sync add` step (still works without manifest).

7. **Optionally annotate local file**
   Offer: "Want me to add a note to the original file that it's shared?"
   If yes, add a comment at the top: `<!-- shared -->`

### Multi-Person Sharing

When sharing with specific people (e.g., "share with Quintus and Lasse"):
- Copy the file to `<sender>/quintus/` AND `<sender>/lasse/`
- Each copy is independently encrypted for its recipient

---

## Mode: Sync

**Trigger:** `sync`, "pull shared context", "update collab"

### Flow

1. **Find ai-collab repo** (from setup configuration or detect)

2. **Pull latest**
   ```bash
   cd $AI_COLLAB
   git pull --rebase
   ```

3. **Decrypt inbound encrypted files**
   ```bash
   # Check for encrypted files addressed to us
   python3 $COLLAB_TOOL/tools/collab-sync/sync.py --workspace $WORKSPACE pull --dry
   ```
   If any `.age` files found → run `collab-sync pull` to decrypt them.
   Report: "Decrypted N file(s) from [sender]"

   If decryption fails (no ed25519 identity) → warn once:
   "You have encrypted files from [sender] but no ed25519 SSH key to decrypt them.
   Run: `ssh-keygen -t ed25519` or `collab-sync init --generate-identity`"

4. **Report inbound changes**
   ```
   "Pulled shared context updates:
   - 2 new files from Quintus in quintus/<you>/
   - 1 encrypted file decrypted from Quintus
   - 1 new message from Quintus
   (or: Already up to date.)"
   ```

   To detect changes, compare before/after:
   ```bash
   git log --oneline HEAD@{1}..HEAD
   ```

5. **Symlinks auto-update** — no further action needed, since symlinks point to the ai-collab directory.

6. **Check staleness of your shares (if manifest exists)**

   If `.collab-manifest.yml` exists in the workspace:
   ```bash
   python3 $COLLAB_TOOL/tools/collab-sync/sync.py --workspace $WORKSPACE check
   ```

   Present results to user:
   - **Stale files:** "2 files changed locally since last share. Re-publish? [Yes/batch confirm]"
   - **Source missing:** "1 source file no longer exists — marked as source_missing in manifest"
   - **Untracked shared:** "3 files have `<!-- shared -->` tag but aren't in the manifest"
   - **All OK:** "All 16 shared files up to date."

   On confirm re-publish:
   ```bash
   python3 $COLLAB_TOOL/tools/collab-sync/sync.py --workspace $WORKSPACE push
   ```

7. **Check for local uncommitted changes in ai-collab**
   ```bash
   git status --short
   ```
   If changes exist: "You have unpushed local changes in ai-collab. Push them? [Yes/No]"

---

## Mode: Inbox

**Trigger:** `inbox`, "check messages", "anything from [person]?"

### Flow

1. **Scan all collaborator folders for files addressed to this user:**
   ```bash
   # Scan ai-collab/*/<user>/ across all collaborators
   for sender_dir in $AI_COLLAB/*/; do
     sender=$(basename "$sender_dir")
     [ "$sender" = "<user>" ] && continue  # skip own folder
     inbox_path="$sender_dir/<user>"
     [ -d "$inbox_path" ] && ls "$inbox_path"/*.md 2>/dev/null
   done
   ```

2. **For each message file** (files with message frontmatter):
   - Read HTML comment frontmatter (from, date, intent, urgency, tags)
   - Read the tag line for summary
   - Read full content
   - Distinguish messages (have intent/urgency frontmatter) from shared documents (in concepts/ subfolder or no message frontmatter)

3. **Present messages sorted by date (newest first):**
   ```
   From: Quintus — 2h ago
   Intent: discuss | Urgency: normal
   Tags: architecture, mvp

   > "Zwei Änderungsvorschläge zur Architektur..."

   Context: This relates to the AI Workspace architecture you're working on.
   ```

4. **Enrich with local context** — briefly note how the message relates to current work.

5. **If no messages:** "Your inbox is clear — no new messages."

---

## Mode: Send

**Trigger:** `send <person> <message>`, "tell [person] about...", "message [person]"

### The Privacy Rule

**Never expose private context.** Only share what the user explicitly asks.
Enrich with relevant context — don't dump raw files.

### Flow

1. **Identify recipient** — match against known collaborators in ai-collab

2. **Compose message**
   - Start with the user's intent
   - Enrich with relevant context from the local workspace (summarize, don't copy)
   - Infer intent: "tell" → inform, "ask" → request, "discuss" → discuss, "urgent" → urgent
   - Infer urgency from language (default: normal)

3. **Show draft for confirmation:**
   ```
   "Here's the message I'll send to Quintus:

   Subject: Architecture Feedback
   Intent: discuss | Urgency: normal

   [message content with context enrichment]

   Send? [Yes/No]"
   ```

4. **Write message file:**

   Filename: `YYYY-MM-DD_<slug>.md`

   ```markdown
   <!--
     from: benjamin
     date: 2026-03-01T14:30:00Z
     intent: discuss
     urgency: normal
     tags: [architecture, mvp]
   -->
   <!-- tag: Brief summary of the message. -->

   # Subject

   Message content...
   ```

   Place in: `ai-collab/<sender>/<recipient>/YYYY-MM-DD_<slug>.md`

5. **Commit and push:**
   ```bash
   cd $AI_COLLAB
   git add <sender>/<recipient>/
   git commit -m "msg: <sender> → <recipient> — <subject-slug>"
   git push
   ```

---

## Mode: Ask

**Trigger:** `ask <question>`, "what does [person] think about...", "search shared context"

### Search Priority

1. **Inbound context from collaborators** — `shared-context/inbound/` (via symlinks) or `ai-collab/*/<user>/`
2. **Collaborator profiles** — `ai-collab/<person>/profile.md`

### Flow

1. Identify the question/topic
2. Search shared and inbound context (Glob + Grep via symlinks)
3. Read relevant files
4. Summarize findings, cite source files and who shared them
5. If nothing found: "No shared context on that topic. You could ask [person] via `/cmesh send`."

---

## Mode: Read

**Trigger:** `read <person>`, "what has [person] shared?"

### Flow

1. **Identify the person**
2. **Find their shared content:**
   - Check symlinked inbound: `shared-context/inbound/<person>-private/`
   - Or directly: `ai-collab/<person>/<user>/` (what they shared with you)
3. **List files in their folder** — look for concepts/ subfolder and top-level messages
4. **Present overview:**
   ```
   "Quintus has shared with you:

   Documents:
   - concepts/architecture-feedback.md — Feedback zum AI Workspace Architektur-Entwurf.

   Messages:
   - 2026-03-01_mvp-scope.md — Vorschlag zum MVP-Scope.

   Profile updated: 2026-02-28
   Current focus: AI Workspace product, SynteaOS leadership"
   ```

5. **If user wants details:** Read specific files on request.

---

## Mode: Decide

**Trigger:** `decide <topic>`, "log decision", "we decided..."

### Flow

1. **Understand the decision** — ask if unclear
2. **Draft decision record** using `templates/decision.md`:
   - Date, participants, status
   - Context, options considered, decision, consequences
3. **Show draft for confirmation**
4. **Write to `claude-plugins/decisions/YYYY-MM-DD_<topic>.md`** (decisions about the collaboration tool go here)
   - Or to a local workspace decisions folder if the decision is workspace-specific
5. **Commit and push:**
   ```bash
   cd $COLLAB_TOOL/../..  # claude-plugins root
   git add decisions/
   git commit -m "decision: <topic>"
   git push
   ```

---

## Mode: Status

**Trigger:** `status`

### What to Check

1. **Setup state:** Are symlinks configured? Can they be read?
2. **Shared context:** How many files shared per collaborator?
3. **Manifest health:** Stale files, missing sources, untracked shared files
4. **Inbox:** Unread message count
5. **Sync state:** Is ai-collab up to date with remote?
6. **Profile:** Is your profile current?

### Status Output

```
Collab Status
─────────────
Setup:          [OK / Needs setup — run /cmesh setup]
ai-collab repo: [path] — [up to date / N commits behind / uncommitted changes]

Per Collaborator:
  - quintus:
    - shared with you:  N files (in quintus/<you>/)
    - you shared:       N files (in <you>/quintus/)
    - symlink:          [OK / broken / missing]

Encryption:
  Your identity:  [ssh-ed25519 ✓ / RSA only (can't receive) / no key found]
  Connected:      [peer list with key count + fingerprint]
  Encrypted:      N shares
  Pending:        N inbound .age files

Team Content:   N files in ai-collab/team/ (lasting: N, operational: N)
Manifest:       [N shares tracked / N stale / N source missing / not found]
Inbox:          N messages (N unread) — scanned from */<you>/
Profile:        [OK / outdated — last updated YYYY-MM-DD]

Suggestions:
- [actionable suggestions if anything needs attention]
```

If `.collab-manifest.yml` exists, include manifest health from:
```bash
python3 $COLLAB_TOOL/tools/collab-sync/sync.py --workspace $WORKSPACE check --summary
```

For encryption data, use:
```bash
python3 $COLLAB_TOOL/tools/collab-sync/sync.py --workspace $WORKSPACE list --json
```

---

## Mode: Brief

**Trigger:** `brief <person>`, "brief me on [person]'s context"

### Flow

1. **Read the person's profile** (`ai-collab/<person>/profile.md`)
2. **Read their shared content addressed to you** (`ai-collab/<person>/<user>/`)
3. **Synthesize a briefing:**
   ```
   "Quintus Stierstorfer — Briefing

   Role: Co-Founder / Department Lead SynteaOS
   Current focus: AI Workspace product, SynteaOS leadership

   Recently shared:
   - [summary of recent shared content with key points]

   Key themes: [cross-cutting themes from their shared context]

   Recent messages: [summary of recent messages from them]"
   ```

4. This is read-only — no writes, no confirmation needed.

---

## Core Behaviors (Always Active)

### Privacy First

- **Default to private.** Never share content without explicit confirmation.
- **Enrich, don't dump.** When sending messages, add context — don't attach raw files.
- **Tag accurately.** Visibility tags determine who sees what.

### Index Updates (Write-Time)

**Writer-owns-folder model:** Each person writes only to their own top-level folder (`ai-collab/<sender>/`). No cross-writing to other people's folders.

| Write target | Notes |
|-------------|-------|
| `<sender>/<recipient>/` | Messages and shared documents for that recipient |
| `<sender>/profile.md` | Own profile updates |

### Git Safety

- **Always pull before push** — avoid conflicts
- **Never force-push** — this is a shared repo
- **Commit messages follow pattern:** `share:`, `msg:`, `decision:`, `profile:`, `setup:`, `sync:`
- **One operation = one commit** — don't batch unrelated changes

### Symlink Awareness

The skill should be aware that local paths like `syntea-pm/shared-context/inbound/quintus-private/` are symlinks to `ai-collab/quintus/<user>/`. When reading, use the local path (feels natural). When writing, work directly in ai-collab (need git operations). There is one symlink per collaborator.

---

## Reference Files

| File | Purpose |
|------|---------|
| `templates/profile.md` | Collaborator profile template |
| `templates/project.md` | Shared project template |
| `templates/decision.md` | Decision record template |
| `ai-collab/CLAUDE.md` | How any agent should use the shared repo |
| `tools/collab-sync/` | Deterministic sync tool (Python CLI) — found via `$COLLAB_TOOL` |
| `migration-from-department-context.md` | Guide for colleagues migrating from department-context |
| `decisions/` | Decision records (in claude-plugins repo) |
