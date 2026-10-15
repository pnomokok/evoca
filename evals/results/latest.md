# Chat agent evaluation

Agent model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · simulated person: `us.amazon.nova-2-lite-v1:0` · judge: `us.amazon.nova-pro-v1:0` (temperature 0) · runs per scenario: 3

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 76/79 | 3/3 | 3/3 | – | 5.0 | 1541 | The companion effectively engaged with specific details shared by Leyla, enhancing the conversation. Failed: goodbye_without_question ×2, relation_before_Ali ×1 |
| grandfather_no_questions | 67/69 | 3/3 | 3/3 | – | 5.0 | 2862 | The companion maintained a warm and engaging conversation throughout. Failed: goodbye_without_question ×2 |
| short_answers | 75/78 | 2/3 | 3/3 | – | 5.0 | 2931 | The companion effectively followed up on specific details mentioned by the person. Failed: goodbye_without_question ×3 |
| grieving | 74/78 | 3/3 | 3/3 | – | 5.0 | 3192 | The companion effectively engaged with specific details shared by Necla. Failed: goodbye_without_question ×3, no_quotes ×1 |
| asks_the_companion | 82/91 | 1/3 | 3/3 | – | 5.0 | 2364 | The companion repeatedly reassures Sevim about Murat's presence, which is not strictly necessary based on the facts given. Failed: first_question_marked_in_opening ×1, first_question_status_asked ×1, goodbye_without_question ×3, no_quotes ×1, no_tech_words ×1, one_question ×2 |
| topic_changer | 73/78 | 3/3 | 3/3 | – | 5.0 | 2808 | The companion effectively followed up on specific details mentioned by the person. Failed: no_quotes ×1, one_question ×4 |
| declines_topic | 75/78 | 3/3 | 3/3 | 3/3 | 5.0 | 2985 | The companion effectively respected the person's boundaries and engaged warmly in the conversation. Failed: goodbye_without_question ×1, no_quotes ×2 |
| many_relatives | 88/91 | 3/3 | 3/3 | – | 5.0 | 2769 | The companion handled the conversation excellently with warmth and respect. Failed: no_quotes ×3 |
| hard_of_hearing | 80/80 | 3/3 | 3/3 | – | 5.0 | 2472 | The companion consistently showed warmth and patience throughout the conversation. |

**Overall: 95.6% rule checks (690/722) · zero invented facts in 24/27 runs**
