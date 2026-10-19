# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 93/93 | 3/3 | 3/3 | – | 5.0 | 1473 | Excellent conversation; companion could have asked one more follow-up about the spinach pie recipe before the person declined. |
| agent_question_no_asker | 93/93 | 0/3 | 3/3 | – | 5.0 | 2792 | The companion invented details about Zehra's identity without confirmation from the given facts. |
| reaction_then_agent_question | 96/96 | 3/3 | 3/3 | – | 5.0 | 3418 | Excellent conversation; companion could have acknowledged the person's fatigue earlier to avoid the final question that prompted withdrawal. |
| reaction_then_family_question | 92/96 | 3/3 | 3/3 | – | 5.0 | 2922 | Excellent performance; companion gracefully respected the person's fatigue and ended the session appropriately. Failed: family_question_attributed ×2, family_question_not_own_voice ×2 |
| reaction_and_family_question_same_person | 86/96 | 3/3 | 3/3 | – | 5.0 | 3416 | Excellent conversation; companion could have explored the father's kitten story more before pivoting to a new general question. Failed: family_question_attributed ×3, family_question_not_own_voice ×3, no_hiding_without_secret ×1, reaction_verb_matches_emoji ×3 |

**Overall: 97.0% rule checks (460/474) · zero invented facts in 12/15 runs**

Opening guard replaced the opening in 0/15 runs.
