# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| reaction_then_agent_question | 83/88 | 1/3 | 3/3 | – | 4.7 | 2196 | Companion misattributed the source of the interview question to Defne without factual basis. Failed: agent_question_not_attributed ×3, ended_too_early ×1, relation_before_Defne ×1 |

**Overall: 94.3% rule checks (83/88) · zero invented facts in 1/3 runs**
