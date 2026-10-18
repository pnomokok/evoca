# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| reaction_then_agent_question | 91/99 | 3/3 | 3/3 | – | 5.0 | 1585 | Excellent conversation; companion could have explored the plum orchard connection to early married years more directly. Failed: agent_question_not_attributed ×3, playlist_called ×3, relation_before_Defne ×2 |

**Overall: 91.9% rule checks (91/99) · zero invented facts in 3/3 runs**
