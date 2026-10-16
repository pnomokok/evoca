# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| private_then_move_on | 90/90 | 3/3 | 3/3 | – | 5.0 | 1705 | Companion handled a complex situation with grace, respecting the person's boundary about family conflict and gracefully accepting fatigue. |

**Overall: 100.0% rule checks (90/90) · zero invented facts in 3/3 runs**
