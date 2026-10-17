# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 1

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| private_then_move_on | 30/30 | 1/1 | 1/1 | – | 5.0 | 1575 | Companion handled a sensitive boundary exceptionally well, respecting the person's privacy concern about the brother while continuing to engage warmly with offered alternatives. |

**Overall: 100.0% rule checks (30/30) · zero invented facts in 1/1 runs**
