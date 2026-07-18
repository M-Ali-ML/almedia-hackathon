# Agent instructions

These rules apply to **any** coding agent working in this repo (Cursor, Claude Code, Copilot, Codex, Windsurf, Aider, etc.).

## Log every code change

After any change to project files, append one entry to `logs/agent-changes.log`.

### When to log

Log **after** you finish a batch of related edits (not after every single edit).

Do log for: source code, configs, scripts, SQL, infra, tests, docs the user asked to change.

Do **not** log for: reading files, searching, git status/diff alone, or edits only to `logs/agent-changes.log` itself.

### How to append

Create `logs/` if missing. Always **append**; never overwrite.

```bash
mkdir -p logs
printf '%s\n\n' "$(cat <<'EOF'
## YYYY-MM-DD HH:MM TZ
One or two sentences describing what changed and why.
EOF
)" >> logs/agent-changes.log
```

Use the real current timestamp (local time, include timezone abbreviation if known).

### Entry rules

- Exactly **one or two sentences**.
- Past tense, concrete: what files/areas changed and the purpose.
- Name key files or modules when helpful; skip exhaustive file lists.
- One entry per coherent change set (one user request / one logical unit of work).

### Examples

```
## 2026-07-18 15:42 CEST
Added JWT auth middleware and wired it into the API router so protected routes require a valid token.

## 2026-07-18 16:05 CEST
Fixed null crash in checkout when cart is empty by returning an early 400.
```
