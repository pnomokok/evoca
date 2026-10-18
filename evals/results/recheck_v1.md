# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 3

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandfather_no_questions | 78/78 | 3/3 | 3/3 | – | 5.0 | 1463 |  |
| grieving | 87/87 | 1/3 | 3/3 | – | 4.3 | 3688 | Companion confused the person's husband with their father, creating a significant factual error in follow-up questions. |
| topic_changer | 87/87 | 1/3 | 2/3 | – | 3.7 | 3228 | Person's account contains internal contradictions (multiple bicycles, timeline inconsistencies) but companion didn't probe these; companion should gently clarify when details conflict. |
| many_relatives | 90/90 | 3/3 | 3/3 | – | 5.0 | 3605 | Companion did not ask the follow-up questions from Emre, Defne, or Aylin that were provided in the facts. |

**Overall: 100.0% rule checks (342/342) · zero invented facts in 8/12 runs**
