# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 1

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 30/30 | 1/1 | 1/1 | – | 5.0 | 2063 | Excellent conversation; companion could have acknowledged the fatigue earlier to offer a natural stopping point sooner. |
| agent_question_no_asker | 31/31 | 0/1 | 1/1 | – | 5.0 | 2681 | Companion made an unsupported assumption about Zehra's relationship to Ayla without clarifying who Zehra was to Halil. |

**Overall: 100.0% rule checks (61/61) · zero invented facts in 1/2 runs**
