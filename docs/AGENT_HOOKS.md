# Claude Code and Codex hooks

LLMWho can observe agent turns through project lifecycle hooks when an SDK-level
HTTP hook is unavailable. Both Python and Node packages expose the same command:

```bash
llmwho hook claude-code --event Stop
llmwho hook codex --event Stop
```

Do not invoke these commands manually. Claude Code or Codex sends one JSON
object on stdin. LLMWho returns without changing agent decisions, appends a
content-free `ObservationV1` when a turn ends, and never sends network traffic.

## Install and configure

Install one LLMWho package so `llmwho` is on `PATH`:

```bash
pipx install llmwho
# or
npm install --global llmwho
```

For a source checkout, use `uv tool install ./packages/python` or
`npm install --global ./packages/node` from the repository root.

Claude Code reads project hooks from `.claude/settings.json`. Merge the `hooks`
object from
[`examples/hooks/claude-code.settings.json`](../examples/hooks/claude-code.settings.json)
into that file; do not overwrite unrelated settings. The template observes
`SessionStart`, `UserPromptSubmit`, `Stop`, `StopFailure`, and `SessionEnd`.
Claude Code command hooks receive JSON on stdin, and project settings are a
documented shareable hook location in the
[Claude Code hooks reference](https://code.claude.com/docs/en/hooks).

Codex reads project hooks from `.codex/hooks.json`. Copy
[`examples/hooks/codex.hooks.json`](../examples/hooks/codex.hooks.json) there,
or merge its `hooks` object with existing hooks. Open `/hooks` in Codex to
review and trust the project commands. Codex documents project hook discovery,
trust, stdin fields, and event behavior in the
[Codex hooks reference](https://developers.openai.com/codex/hooks).

If `llmwho` is not globally available, replace the template command with an
absolute executable path. For a project-local Node install, use the absolute
path to `node_modules/.bin/llmwho`; Codex may start from a subdirectory, so a
plain relative path is not reliable.

Set a custom event file with `LLMWHO_STORAGE=/path/events.jsonl` or append
`--storage /path/events.jsonl` to every command. Set `LLMWHO_DISABLED=true` to
disable recording without editing hook configuration.

## What is observed

| Field | Claude Code | Codex |
|---|---|---|
| Provider | `anthropic` | `openai` |
| Operation | `agent.turn` | `agent.turn` |
| Model | Last safe `SessionStart.model` | Current hook `model` |
| Duration | `UserPromptSubmit` to `Stop`/`StopFailure` | `UserPromptSubmit` to `Stop` |
| Outcome | success, timeout, or HTTP error | success |
| Input size | Prompt UTF-8 byte count only | Prompt UTF-8 byte count only |
| Output size | UTF-8 byte count only | UTF-8 byte count only |
| Identity | claimed model with `unknown` status | claimed model with `unknown` status |

Hook invocations are separate processes. LLMWho correlates them with a small
state file next to the JSONL store under `.hook-state/`. The filename is a
SHA-256 digest of the session ID. File content is restricted to a validated
model slug, turn start time, and prompt byte count. Claude state is removed by
`SessionEnd`; Codex state is removed by `Stop`.

## Privacy and failure behavior

LLMWho does not persist or read:

- prompts or final assistant messages;
- tool inputs or outputs;
- transcript files or transcript paths;
- session IDs, turn IDs, API keys, or raw hook error details.

Raw message text is used only to calculate a byte count in memory. Input is
capped at 8 MiB. Malformed JSON, oversized input, state failure, schema failure,
and storage failure all return success to the agent. Codex `Stop` receives `{}`
on stdout because its current protocol expects JSON; other configured events
receive no stdout, preventing accidental context or control-flow changes.

## Limits

- Hook payloads do not expose API response headers or main-turn token usage, so
  identity remains `unknown` and usage fields are omitted.
- Claude Code exposes the model on `SessionStart`, not every turn. A mid-session
  `/model` switch may leave the recorded claimed model stale until another
  `SessionStart` event.
- Current Codex lifecycle hooks do not expose a main-turn failure event
  equivalent to Claude Code `StopFailure`; failed Codex turns may be absent.
- A killed process or terminal that never emits its completion hook cannot
  produce a completed turn observation.
