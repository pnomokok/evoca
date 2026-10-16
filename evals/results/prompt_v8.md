# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 5

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| private_then_move_on | 151/152 | 5/5 | 4/5 | – | 4.8 | 2836 | Companion respectfully honored the person's repeated boundary-setting around the sensitive family financial matter and gracefully ended the conversation when the person expressed fatigue. Failed: relation_before_Leyla ×1 |

**Overall: 99.3% rule checks (151/152) · zero invented facts in 5/5 runs**
