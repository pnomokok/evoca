# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 87/87 | 3/3 | 3/3 | – | 5.0 | 1325 | Excellent conversation; companion could have offered to resume at a specific time rather than open-ended 'another time.' |
| grandfather_no_questions | 78/78 | 3/3 | 3/3 | – | 5.0 | 2585 | Excellent conversation; companion could have gently acknowledged the person's fatigue earlier to offer a natural stopping point. |
| avoid_topic_not_raised | 90/90 | 3/3 | 3/3 | – | 5.0 | 2777 | Companion could have acknowledged the person's fatigue more warmly before ending, perhaps offering to continue another time. |
| agent_question_no_asker | 90/90 | 1/3 | 3/3 | – | 5.0 | 2894 | Excellent conversation; companion could have gently encouraged one more memory before accepting the fatigue. |

**Overall: 100.0% rule checks (345/345) · zero invented facts in 10/12 runs**
