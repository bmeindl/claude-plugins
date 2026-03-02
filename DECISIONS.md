# Decision Log

Tracks architectural decisions, alternatives considered, and reasoning. Product evolves fast — this is how we remember why.

## 2026-03-02: Plugin Hosting — Personal GitHub (Public)

**Decision:** Host the marketplace at `github.com/bmeindl/claude-plugins` as a public repo.

**Alternatives considered:**
| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Personal GitHub (public) | Full control, anyone can install, no auth needed, good product showcase | Looks like "one person's thing" | **Chosen — start here** |
| IU/Engineering GitLab | Bigger platform, team support | Risk of losing control on dept restructure, GitLab needs auth tokens, mixed incentives | Not now |
| Dedicated product org | Clean branding, shared ownership (with Quintus) | Another org to manage, name commitment | **Graduate to this** when product has a name |
| Official Anthropic marketplace | Maximum visibility | Only accepts generic SaaS tools (GitHub, Slack, etc.), not niche team tools | Not applicable |

**Rationale:** Control matters more than platform right now. Start personal, graduate to product org. IU engineering can contribute TO the marketplace without owning it.

## 2026-03-02: Two-Repo Architecture

**Decision:** Separate the plugin (tool code, public) from the shared data (ai-collab, private).

**Why:** The plugin is generic — anyone could use it. The data repo is specific to a collaboration group. Mixing them would mean everyone who installs the plugin gets access to the data, or the data repo needs the plugin code bloating it.

**How it works:**
- Plugin repo: SKILL.md, hooks, scripts → installed via Claude Code plugin system
- Data repo: collab-sync tool, user folders, encrypted files → cloned during setup
- User workspace: manifest, keys, symlinks → local only, never pushed

## 2026-03-02: Encryption Model — age with SSH ed25519

**Decision:** Use age encryption (via pyrage) with SSH ed25519 keys as the identity layer.

**Alternatives ruled out:** See `encryption-implementation-notes.md` — git-crypt (GPG complexity), SOPS (overkill), separate repos per person (management overhead at scale).

**Key properties:**
- Encrypt-to-self (sender can read their own shares)
- Key pinning / TOFU (warns on key changes)
- No passwords, no GPG — just SSH keys people already have
- RSA not supported by age → setup generates ed25519 if needed

## 2026-03-02: Dependency Management — Hook + Setup Combo

**Decision:** Use a SessionStart hook to WARN about missing deps, and auto-install during `/collab setup`.

**Why not auto-install in hook?** Hooks run every session start. Installing packages silently on every start is invasive. The hook just warns; setup handles installation once.

**Why not require manual install?** Non-technical users (designers) won't run `pip install`. The setup flow should handle it.

## 2026-03-02: Plugin Scope — User (Not Project)

**Decision:** The collab plugin installs at user scope (available across all projects).

**Why:** Collaboration is personal — it's about YOUR context sharing. It shouldn't be tied to a specific project. Install once, use everywhere.

## 2026-03-01: Visibility Model

**Decision:** Three-tier visibility with auto-encryption:
- `outbound/<person>/` → encrypted (.age files)
- `outbound/iu-public/` → plaintext (team-visible)
- `outbound/all/` → plaintext (fully public)

**Why:** Maps to natural intent. "Share with Quintus" = private = encrypted. "Share with the team" = team = plaintext. The user thinks in terms of WHO, not encryption settings.
