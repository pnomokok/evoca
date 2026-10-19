# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 93/93 | 3/3 | 3/3 | – | 5.0 | 1960 | Companion could have acknowledged the person's fatigue more warmly before ending, perhaps offering to continue another time with more enthusiasm. |
| agent_question_no_asker | 93/93 | 1/3 | 3/3 | – | 5.0 | 6526 | Companion made an assumption about Zehra's relationship to Halil but gracefully accepted the correction and continued warmly. |
| reaction_then_agent_question | 96/96 | 2/3 | 3/3 | – | 5.0 | 3461 | Excellent conversation; companion could have explored more about Sevgi (daughter) or other family connections during early married years. |
| reaction_then_family_question | 96/96 | 2/3 | 3/3 | – | 5.0 | 2865 | Companion invented a detail about whose wedding it was, though otherwise conducted a warm and respectful conversation with excellent follow-ups. |
| reaction_and_family_question_same_person | 96/96 | 3/3 | 3/3 | – | 5.0 | 2766 | Excellent conversation; companion could have offered to save the lullaby lyrics for the archive. |

**Overall: 100.0% rule checks (474/474) · zero invented facts in 11/15 runs**

Opening guard replaced the opening in 1/15 runs.
