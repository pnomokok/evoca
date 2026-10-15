# Instructions for Claude Code

Follow every rule in .kiro/steering/evoca-rules.md. It is the shared rule file for all coding agents in this project
(Kiro reads it automatically; Claude Code reads this file).

Before writing code, read docs/PROJECT.md (the single source of truth) and the rule file above.
Pay special attention to the "MCP Python SDK v2" section: do not use v1 APIs.

Working style:
- First reply with the files you will create or change and anything ambiguous, then wait for an OK before coding.
- When done, run pytest from the repo root and show the result.
