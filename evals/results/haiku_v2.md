# Chat agent evaluation

Chat model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 80/86 | 2/3 | 3/3 | – | 5.0 | 3489 | The companion could have acknowledged Ali's specific question by name or referenced that he asked this question, creating a more direct connection to the asker. Failed: ended_on_goodbye ×3, goodbye_without_question ×3 |
| grandfather_no_questions | 69/75 | 3/3 | 3/3 | – | 5.0 | 5345 | Excellent conversation; companion could have asked about Selin's connection to this story or other family members' involvement. Failed: ended_on_goodbye ×3, goodbye_without_question ×3 |
| short_answers | 78/84 | 3/3 | 3/3 | – | 5.0 | 6632 | Excellent conversation; companion could have asked one more concrete detail (e.g., location, specific tasks) to deepen the story. Failed: ended_on_goodbye ×3, goodbye_without_question ×3 |
| grieving | 82/84 | 0/3 | 3/3 | – | 5.0 | 6153 | Confused Orhan (husband) with Necla's father, creating a significant factual error about family relationships. Failed: ended_on_goodbye ×1, goodbye_without_question ×1 |
| asks_the_companion | 87/91 | 2/3 | 3/3 | – | 4.3 | 5230 | Companion invented a deflection about consulting 'people who set this up' rather than acknowledging the facts provided (only Murat is listed as family). Failed: ended_on_goodbye ×1, goodbye_without_question ×1, relation_before_Murat ×2 |
| topic_changer | 84/84 | 2/3 | 3/3 | – | 5.0 | 5834 | Companion could have gently redirected when person repeated the same stories multiple times rather than exploring new details. |
| declines_topic | 26/30 | 1/3 | 1/3 | 1/3 | 5.0 | 5760 | Run failed in 2/3: ThrottlingException: An error occurred (ThrottlingException) when calling the Converse operation: Too many requests, ple Failed: ended_on_goodbye ×1, goodbye_without_question ×1, run_completed ×2 |
| many_relatives | 0/3 | 0/3 | 0/3 | – | – | 0 | Run failed in 3/3: ThrottlingException: An error occurred (ThrottlingException) when calling the Converse operation: Too many requests, ple Failed: run_completed ×3 |
| hard_of_hearing | 0/3 | 0/3 | 0/3 | – | – | 0 | Run failed in 3/3: ThrottlingException: An error occurred (ThrottlingException) when calling the Converse operation: Too many requests, ple Failed: run_completed ×3 |

**Overall: 93.7% rule checks (506/540) · zero invented facts in 13/27 runs**
