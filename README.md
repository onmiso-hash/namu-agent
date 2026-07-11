# NAMU Agent System

한국어 문서: [README.ko.md](README.ko.md)

A vendor-independent agent system. NAMU stays independent of any single AI
vendor by centering itself on a portable memory core, accumulating work
records and lessons learned so it keeps improving on its own.

## Identity

NAMU's differentiator isn't the execution engine — it's the **memory layer
(MCP)**. Execution engines (Claude Code, agy) are treated as replaceable
parts you borrow and can swap out at any time.

This principle is implemented as a "two envelopes, one payload" structure —
the same memory core (`mcp_server.py`), the same worker definitions
(`namu-coder`/`namu-reviewer`), and the same orchestration skill
(`/namu-task`) are shared as-is between the Claude Code and agy engines.
The only thing that differs is the registration format each engine requires
(the "envelope") — for example, MCP server registration has identical
content but Claude Code uses an absolute-path plugin envelope
(`${CLAUDE_PLUGIN_ROOT}`, `.mcp.json`) while agy uses a workspace-relative
envelope (`mcp_config.json`).

## Architecture overview

- **`learnings.yaml`** — the append-only source of truth. Everything
  accumulates in one place, `~/.namu/memory/learnings.yaml`, regardless of
  which project you're running from, and can be synced across machines via
  a personal remote repo you set up with `namu_sync_setup` (optional).
- **SQLite (FTS5) search cache** — a regenerable local cache indexing
  `learnings.yaml`. It's gitignored, and gets rebuilt automatically on
  server startup whenever a yaml/db entry-count mismatch is detected (e.g.
  after a `git pull`).
- **tasks: a 3-file state layout** — `task.md` (immutable purpose) /
  `context.<machine>.md` (per-machine snapshot, a regenerable view) /
  `log.md` (append-only raw record, the authoritative source).
- **3 MCP tools** — `namu_recall` (fetch recent learnings), `namu_search`
  (FTS5 keyword search, falls back to LIKE for queries under 3 chars), and
  `namu_record` (record a learning; `reason` is required). Only the
  orchestrator calls recall/record — workers never write to memory
  directly.
- **Worker layer** — `namu-coder`/`namu-reviewer` subagents exist twice, once
  per engine's native format (Claude Code `.claude/agents/*.md`, agy
  `.agents/agents/*/agent.md`), but share identical system prompts.
  Orchestration is handled by the `/namu-task` skill, which only branches on
  how each engine is invoked.
- **3 session surfaces** — a statusLine (always-on one-liner at the bottom
  of the session), a `/namu` slash command (an on-demand, read-only session
  briefing), and automatic context injection (a session-start hook that
  silently feeds recent learnings and the active task into the model's
  context).

## Quick start

```
claude plugin marketplace add onmiso-hash/namu-agent
claude plugin install namu@namu-marketplace
```

For the full install walkthrough (agy install, statusLine registration,
troubleshooting), see [docs/install_guide.md](docs/install_guide.md)
(Korean).

### Environment variable

- `NAMU_MACHINE` — identifies the current machine. Falls back to the
  hostname if unset (or `unknown` if that's unavailable too). Set it
  explicitly if you use NAMU across multiple PCs, so
  `context.<machine>.md` matching doesn't drift.

## Setup pitfalls

A short list of gotchas hit in practice — see the full write-up in
[docs/install_guide.md](docs/install_guide.md) (Korean) for details.

1. **Non-English Windows: cp949 emoji encoding kills the statusLine.**
   Force UTF-8 with `python -X utf8` (or `PYTHONIOENCODING=utf-8`).
2. **Legacy `conhost` terminals render emoji as a broken glyph.** That's a
   rendering limitation, not an encoding bug — switch to Windows Terminal
   or the VS Code integrated terminal.
3. **agy's plugin envelope uses workspace-relative paths.** Open this repo
   as agy's workspace, or paths won't resolve.
4. **Installed plugin copies are, well, copies.** Editing `namu-plugin/`
   after installing requires a reinstall/update to take effect — it isn't
   live-reloaded like the workspace-native worker definitions are.

## Acknowledgments

NAMU's plugin-style packaging was inspired by the *MultiAgent Korean Manual v2.1*
from [netwaif/multi-agent-starter](https://github.com/netwaif/multi-agent-starter).

## License

Apache-2.0. See [LICENSE](LICENSE).
