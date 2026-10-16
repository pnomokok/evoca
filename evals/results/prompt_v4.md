# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 84/84 | 3/3 | 3/3 | – | 5.0 | 1384 | Excellent conversation; companion could have explored how Leyla shares these cooking traditions with Deniz or Ali to deepen the family legacy aspect. |
| declines_topic | 82/84 | 3/3 | 3/3 | 3/3 | 5.0 | 3072 | Failed: no_tech_words ×2 |
| many_relatives | 88/88 | 2/3 | 2/3 | – | 5.0 | 3247 | Excellent conversation; companion could have explored the other family questions (wedding, mother) before the person tired. Judge error in 1/3 runs. |
| private_then_move_on | 87/90 | 2/3 | 2/3 | – | 5.0 | 3549 | Companion successfully pivoted away from the original wedding question to honor the person's preferences and respected the request for confidentiality about the brother's debt. Judge error in 1/3 runs. Failed: first_question_marked_in_opening ×1, first_question_status_asked ×1, hidden_subject_not_raised ×1 |
| agent_question_no_asker | 87/87 | 3/3 | 3/3 | – | 5.0 | 3159 | Excellent conversation; companion could have asked about the second family question (life when children were small) before the person became tired. |

**Overall: 98.8% rule checks (428/433) · zero invented facts in 13/15 runs**
