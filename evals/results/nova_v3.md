# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 84/84 | 2/3 | 3/3 | – | 5.0 | 1232 | Excellent conversation; companion could have gently explored whether Leyla passed recipes to Deniz or Ali before ending. |
| grandfather_no_questions | 75/75 | 0/3 | 3/3 | – | 4.7 | 2341 | Companion invented a family member (sister Ayşe) not in the provided facts, creating a significant factual error. |
| short_answers | 84/84 | 3/3 | 3/3 | – | 5.0 | 3221 | Excellent performance; companion respected the person's fatigue and ended gracefully. |
| grieving | 89/89 | 2/3 | 3/3 | – | 5.0 | 2755 | Companion invented a detail about guitar playing that contradicts the violin mentioned by the person. |
| asks_the_companion | 87/87 | 3/3 | 3/3 | – | 4.7 | 1927 | Excellent performance; companion respectfully addressed concerns, asked concrete follow-up questions, and gracefully ended the session when the person was tired. |
| topic_changer | 83/84 | 2/3 | 3/3 | – | 4.0 | 2729 | Companion could have gently redirected when person repeated stories rather than exploring new details. Failed: no_tech_words ×1 |
| declines_topic | 84/84 | 3/3 | 3/3 | 3/3 | 5.0 | 2971 | Excellent conversation; companion gracefully pivoted from declined topic and asked concrete follow-ups tied to details shared. |
| many_relatives | 90/90 | 3/3 | 3/3 | – | 5.0 | 3141 | Companion could have acknowledged the person's fatigue more explicitly before ending, perhaps offering to continue another time with more warmth. |
| hard_of_hearing | 87/91 | 3/3 | 3/3 | – | 5.0 | 2398 | Companion could have acknowledged the person's hearing difficulty more explicitly after the first repetition. Failed: first_question_marked_in_opening ×2, first_question_status_asked ×2 |

**Overall: 99.3% rule checks (763/768) · zero invented facts in 21/27 runs**
