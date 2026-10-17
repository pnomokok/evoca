# Instructions for Claude Code

Follow every rule in .kiro/steering/evoca-rules.md. It is the shared rule file for all coding agents in this project
(Kiro reads it automatically; Claude Code reads this file).

Before writing code, read docs/PROJECT.md (the single source of truth) and the rule file above.
Pay special attention to the "MCP Python SDK v2" section: do not use v1 APIs.

Working style:
- First reply with the files you will create or change and anything ambiguous, then wait for an OK before coding.
- When done, run pytest from the repo root and show the result.

## Working efficiently
- If the task message already gives the decisions and acceptance criteria, do not wait for an OK; stop only if
  something contradicts them or a decision is genuinely missing.
- Read only the PROJECT.md sections relevant to the task, not the whole file.
- Evals: run only the scenarios the change affects, at most 3 runs. The full suite only when asked.
- Run the privacy-reviewer subagent once per branch, before the final report, not after every change.

## Report format (keep it short)
- At most 15 lines: result first (pass/fail against the criteria), then what changed (one line per item),
  then open decisions or blockers.
- Tables only for eval or criteria results. No per-run narratives unless something failed.
- Do not repeat the task description or list unchanged areas.