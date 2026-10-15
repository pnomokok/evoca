# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 79/84 | 3/3 | 3/3 | – | 5.0 | 1397 | Excellent conversation; companion could have occasionally asked about other family members (Deniz, the son) to broaden the family story collection. Failed: ended_on_goodbye ×3, goodbye_without_question ×2 |
| grandfather_no_questions | 69/75 | 3/3 | 3/3 | – | 5.0 | 2699 | Excellent conversation; companion could have asked more about Hasan's daughter Selin or how these stories connect to family. Failed: ended_on_goodbye ×3, goodbye_without_question ×3 |
| short_answers | 73/84 | 3/3 | 3/3 | – | 4.3 | 3299 | Follow-up about keeping in touch shifts away from the person's concrete memories; could have asked more about specific friend interactions or mill experiences. Failed: ended_on_goodbye ×3, first_question_marked_in_opening ×2, first_question_status_asked ×2, goodbye_without_question ×3, no_tech_words ×1 |
| grieving | 81/87 | 3/3 | 3/3 | – | 5.0 | 3251 | Excellent conversation; companion could have explored Ece's perspective or asked about Necla's life beyond Orhan to add dimension. Failed: ended_on_goodbye ×3, goodbye_without_question ×3 |
| asks_the_companion | 91/98 | 0/3 | 3/3 | – | 3.3 | 1642 | Companion failed to address the person's repeated concerns about privacy and the nature of the technology, which caused visible anxiety throughout the conversation. Failed: ended_on_goodbye ×3, first_question_marked_in_opening ×2, first_question_status_asked ×2 |
| topic_changer | 83/84 | 2/3 | 3/3 | – | 4.7 | 2208 | Companion occasionally misremembered or contradicted details the person provided (e.g., football match outcome), though generally warm and attentive to specific memories mentioned. Failed: ended_on_goodbye ×1 |
| declines_topic | 79/84 | 3/3 | 3/3 | 3/3 | 5.0 | 3201 | Failed: ended_on_goodbye ×3, goodbye_without_question ×2 |
| many_relatives | 95/100 | 2/3 | 3/3 | – | 4.3 | 3023 | Companion repeatedly addresses Emre directly despite speaking with Fikriye, and misgendered Defne as nephew instead of niece. Failed: ended_on_goodbye ×2, goodbye_without_question ×2, relation_before_Defne ×1 |
| hard_of_hearing | 78/86 | 3/3 | 3/3 | – | 5.0 | 2251 | Companion could have acknowledged the person's hearing difficulties more proactively by speaking more clearly initially. Failed: ended_on_goodbye ×3, first_question_marked_in_opening ×1, first_question_status_asked ×1, goodbye_without_question ×3 |

**Overall: 93.1% rule checks (728/782) · zero invented facts in 22/27 runs**
