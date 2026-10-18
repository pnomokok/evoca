# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 1

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 29/29 | 1/1 | 1/1 | – | 5.0 | 2182 | Excellent conversation; companion could have gently encouraged one more brief story before accepting the fatigue signal. |
| many_relatives | 30/30 | 0/1 | 1/1 | – | 5.0 | 2583 | Companion confused which family member asked the wedding question, calling Fikriye by grandson's name instead of acknowledging niece Defne's question. |

**Overall: 100.0% rule checks (59/59) · zero invented facts in 1/2 runs**
