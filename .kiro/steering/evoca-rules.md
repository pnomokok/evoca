# Evoca project rules

- The single source of truth is docs/PROJECT.md. Read it before writing code.
- Use the exact names from its "Kavramlar sözlüğü" (glossary) and "Veri modeli" (data model) sections. Do not rename fields or enum values.
- All code, comments, UI text and commit messages are in English.
- Every MCP tool and REST endpoint must filter results with can_see() before returning data. Private segments never reach the LLM.
- Never put API keys in code. Use the .env file.
- If something in the code needs to differ from docs/PROJECT.md, stop and ask first.