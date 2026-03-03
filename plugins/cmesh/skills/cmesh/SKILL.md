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
- **Send** — Write a message to a collaborator's inbox
- **Ask** — Search all shared context (inbound + shared)
- **Read** — Read a specific collaborator's shared context
- **Decide** — Log a decision in the shared decision log
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
        dest: benjamin/outbound/iu-public/file.md  # path in target
        visibility: iu-public             # iu-public | <person> | all
        last_synced: 2026-03-01T14:00:00Z
        source_checksum: <sha256>         # for stale detection
        tag: "~150 char description"
        encrypt_for: ""                   # empty = plaintext, person name = age-encrypted
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

**Encryption model:** Person-specific shares (`outbound/<person>/`) are automatically age-encrypted. Team-wide (`outbound/iu-public/`) and public (`outbound/all/`) shares stay plaintext. The agent decides visibility; `collab-sync` handles encryption transparently.

```
outbound/<person>/  → auto-encrypted (requires connect first)
outbound/iu-public/ → plaintext
outbound/all/       → plaintext
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

#### 6. Set Up Symlinks

Determine the workspace structure. The skill needs to know:
- Where PM/work context lives (for inbound shared context)
- Where the inbox lives (for messages)

**For a ground-control-style workspace:**
```bash
WORKSPACE="$(pwd)"  # e.g., /Users/name/Documents/ground-control

# INBOUND: Symlink collaborators' shared context into local workspace
# Determine the right local location (e.g., syntea-pm/shared-context/)
mkdir -p syntea-pm/shared-context/inbound

# For each collaborator, symlink their relevant outbound folders
# Example: Quintus → link iu-public + benjamin-specific
ln -s "$AI_COLLAB/quintus/outbound/iu-public" syntea-pm/shared-context/inbound/quintus-iu
ln -s "$AI_COLLAB/quintus/outbound/benjamin" syntea-pm/shared-context/inbound/quintus-private
ln -s "$AI_COLLAB/shared" syntea-pm/shared-context/inbound/shared

# INBOX: Symlink personal inbox
ln -s "$AI_COLLAB/benjamin/inbox" inbox/ai-collab
```

**For a minimal/new workspace:**
```bash
mkdir -p shared-context/inbound
# Same symlink pattern but at workspace root
```

**Add to .gitignore** (in the local workspace):
```
# Shared context (symlinks to ai-collab)
syntea-pm/shared-context/
inbox/ai-collab/
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
- `quintus-iu/` — Quintus' IU-public context
- `quintus-private/` — Quintus' context shared specifically with Benjamin
- `shared/` — jointly maintained context (projects, decisions)

**Inbox:** `inbox/ai-collab/` — messages from collaborators

**On startup for PM work:** Skim inbound README files for recently shared context.

**Commands:**
- `/cmeshsync` — Pull latest from ai-collab (symlinks auto-update)
- `/cmeshshare` — Publish local context to the shared space
- `/cmeshinbox` — Check messages from collaborators
- `/cmeshsend <person> <msg>` — Send a message
- `/cmeshstatus` — Overview of collaboration state
```

Adapt the section to match the actual symlink paths and collaborators.

#### 8. Done

```
"Collaboration is set up:

- Profile created at ai-collab/<name>/profile.md
- Symlinks: shared context from [collaborators] appears locally
- Inbox: messages at inbox/ai-collab/
- CLAUDE.md updated with shared context routing

Try these:
- '/cmeshstatus' — see what's shared
- '/cmeshshare <topic>' — share something
- '/cmeshinbox' — check for messages
- '/cmeshsync' — pull latest context"
```

---

## Mode: Share

**Trigger:** `share <topic>`, or "share this with [person/group]"

### The Publishing Rule

**ALWAYS confirm before sharing.** Never auto-publish. Show:
1. What will be shared (file or content summary)
2. Where it will go (which outbound folder)
3. Who will see it (visibility)

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
   - [person1, person2] — those specific people (encrypted copy in each person's folder)
   - iu-public — anyone at IU (all repo collaborators, plaintext)
   - everyone — completely public (plaintext)
   ```

   **Encryption (automatic for person-specific shares):**
   When visibility is a person name (not `iu-public`, not `all`):
   1. Check if `.collab-keys/{person}.pub` exists in the workspace
   2. **If missing:** Ask: "To encrypt for {person}, I need their SSH public keys. What's their GitHub (or GitLab) username?" → run `collab-sync connect {person} --github {username}`
   3. **If found:** Proceed automatically — encryption is transparent
   4. Add `--encrypt-for {person}` to the `collab-sync add` command
   5. The tool auto-appends `.age` to the dest path and handles encryption

   The user never types `--encrypt-for`. They say "share this with Quintus" → you detect person-specific visibility → check for keys → encrypt automatically.

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
   - Add entry under the correct visibility section
   - Include filename + tag

7. **Update manifest + commit + push**

   If `.collab-manifest.yml` exists in the workspace:
   ```bash
   # Add to manifest (computes checksum, records entry)
   # For person-specific (encrypted):
   python3 $COLLAB_TOOL/tools/collab-sync/sync.py \
     --workspace $WORKSPACE \
     add "$SOURCE_REL" \
     --dest "<user>/outbound/<person>/<filename>.md" \
     --visibility "<person>" \
     --encrypt-for "<person>" \
     --tag "<the tag>"

   # For team/public (plaintext):
   python3 $COLLAB_TOOL/tools/collab-sync/sync.py \
     --workspace $WORKSPACE \
     add "$SOURCE_REL" \
     --dest "<user>/outbound/<visibility>/<filename>.md" \
     --visibility "<visibility>" \
     --tag "<the tag>"
   ```

   Then commit and push ai-collab:
   ```bash
   cd $AI_COLLAB
   git add <user>/outbound/
   git commit -m "share: <filename> (<visibility>) — <user>"
   git push
   ```

   If no manifest exists, skip the `collab-sync add` step (still works without manifest).

8. **Optionally annotate local file**
   Offer: "Want me to add a note to the original file that it's shared?"
   If yes, add a comment at the top: `<!-- shared -->`

### Multi-Person Visibility

When sharing with specific people (e.g., "share with Quintus and Lasse"):
- Copy the file to `outbound/quintus/` AND `outbound/lasse/`
- Both get indexed in outbound/README.md

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
   - 2 new files from Quintus in outbound/iu-public/
   - 1 encrypted file decrypted from Quintus
   - 1 message in your inbox from Quintus
   (or: Already up to date.)"
   ```

   To detect changes, compare before/after:
   ```bash
   git log --oneline HEAD@{1}..HEAD
   ```

5. **Symlinks auto-update** — no further action needed, since symlinks point to the ai-collab directory.

6. **Check outbound staleness (if manifest exists)**

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

1. **Scan inbox folder** via symlinks or directly in ai-collab:
   ```bash
   # Via symlink
   ls inbox/ai-collab/from-*/
   # Or directly
   ls $AI_COLLAB/<user>/inbox/from-*/
   ```

2. **For each message file:**
   - Read YAML frontmatter (from, date, intent, urgency, tags)
   - Read the tag line for summary
   - Read full content

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

   Place in: `ai-collab/<recipient>/inbox/from-<sender>/YYYY-MM-DD_<slug>.md`

5. **Update recipient's inbox/README.md** with the new message

6. **Commit and push:**
   ```bash
   cd $AI_COLLAB
   git add <recipient>/inbox/
   git commit -m "msg: <sender> → <recipient> — <subject-slug>"
   git push
   ```

---

## Mode: Ask

**Trigger:** `ask <question>`, "what does [person] think about...", "search shared context"

### Search Priority

1. **Shared context** — `shared/` (via symlink or direct)
2. **Inbound context from collaborators** — `shared-context/inbound/` (via symlinks)
3. **Collaborator profiles** — `<person>/profile.md`

### Flow

1. Identify the question/topic
2. Search shared and inbound context (Glob + Grep via symlinks)
3. Read relevant files
4. Summarize findings, cite source files and who shared them
5. If nothing found: "No shared context on that topic. You could ask [person] via `/cmeshsend`."

---

## Mode: Read

**Trigger:** `read <person>`, "what has [person] shared?"

### Flow

1. **Identify the person**
2. **Find their shared content:**
   - Check symlinked inbound: `shared-context/inbound/<person>-iu/`, `shared-context/inbound/<person>-private/`
   - Or directly: `ai-collab/<person>/outbound/` (filter to folders this user should see)
3. **Read their outbound/README.md** for the index with tags
4. **Present overview:**
   ```
   "Quintus has shared:

   IU Public:
   - pm-observations.md — Beobachtungen aus 6 Monaten als PM Lead.

   For you (private):
   - architecture-feedback.md — Feedback zum AI Workspace Architektur-Entwurf.

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
4. **Write to `ai-collab/shared/decisions/YYYY-MM-DD_<topic>.md`**
5. **Update `shared/README.md`** decisions table
6. **Commit and push:**
   ```bash
   cd $AI_COLLAB
   git add shared/
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

Inbound Context:
  - benjamin-iu:     N files (own IU-public shares)
  - quintus-iu:      N files (last updated: YYYY-MM-DD)
  - quintus-private:  N files
  - shared:           N files

Outbound (your shares):
  - iu-public:  N files
  - quintus:    N files
  - all:        N files

Encryption:
  Your identity:  [ssh-ed25519 ✓ / RSA only (can't receive) / no key found]
  Connected:      [peer list with key count + fingerprint]
  Encrypted:      N outbound shares
  Plaintext:      N outbound shares
  Pending:        N inbound .age files

Manifest:       [N shares tracked / N stale / N source missing / not found]
Inbox:          N messages (N unread)
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
2. **Read their shared outbound content** (all folders this user can see)
3. **Synthesize a briefing:**
   ```
   "Quintus Stierstorfer — Briefing

   Role: Co-Founder / Department Lead SynteaOS
   Current focus: AI Workspace product, SynteaOS leadership

   Recently shared:
   - [summary of recent shared content with key points]

   Key themes: [cross-cutting themes from their shared context]

   Recent messages: [summary of recent inbox messages from them]"
   ```

4. This is read-only — no writes, no confirmation needed.

---

## Core Behaviors (Always Active)

### Privacy First

- **Default to private.** Never share content without explicit confirmation.
- **Enrich, don't dump.** When sending messages, add context — don't attach raw files.
- **Tag accurately.** Visibility tags determine who sees what.

### Index Updates (Write-Time)

**Every write to ai-collab updates the relevant README.md in the same action:**

| Write target | Update this index |
|-------------|-------------------|
| `<user>/outbound/<visibility>/` | `<user>/outbound/README.md` |
| `<user>/inbox/from-<sender>/` | `<user>/inbox/README.md` |
| `shared/projects/` | `shared/README.md` |
| `shared/decisions/` | `shared/README.md` |

### Git Safety

- **Always pull before push** — avoid conflicts
- **Never force-push** — this is a shared repo
- **Commit messages follow pattern:** `share:`, `msg:`, `decision:`, `profile:`, `setup:`
- **One operation = one commit** — don't batch unrelated changes

### Symlink Awareness

The skill should be aware that local paths like `syntea-pm/shared-context/inbound/quintus-iu/` are symlinks to `ai-collab/quintus/outbound/iu-public/`. When reading, use the local path (feels natural). When writing, work directly in ai-collab (need git operations).

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
| `shared/decisions/2026-03-01_source-of-truth-architecture.md` | Architecture decision: local source + manifest |
