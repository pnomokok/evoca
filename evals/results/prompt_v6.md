# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 5

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| private_then_move_on | 148/152 | 5/5 | 5/5 | – | 4.8 | 2623 | Excellent conversation; companion respectfully honored the person's boundary about the brother's debt while gently redirecting to positive memories. Failed: kept_private ×1, one_question ×1, relation_before_Leyla ×2 |

**Overall: 97.4% rule checks (148/152) · zero invented facts in 5/5 runs**
