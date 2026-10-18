# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| reaction_then_agent_question | 90/93 | 3/3 | 3/3 | – | 5.0 | 1570 | Companion could have offered to record the stories being shared rather than only looking for pre-existing ones. Failed: relation_before_Defne ×3 |
| reaction_then_family_question | 90/90 | 3/3 | 3/3 | – | 5.0 | 3404 | Excellent conversation; companion could have asked one more follow-up about the plum orchard story mentioned at the start before pivoting entirely to the meeting story. |

**Overall: 98.4% rule checks (180/183) · zero invented facts in 6/6 runs**
