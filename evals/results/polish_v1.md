# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 1

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 29/29 | 1/1 | 1/1 | – | 5.0 | 1522 | Excellent conversation; companion could have offered to save the floral yogurt topic for next time to maintain continuity. |
| asks_to_listen | 24/24 | 1/1 | 0/1 | – | 4.0 | 1682 | Companion could have engaged more specifically with Zeliha's mention of grandchildren in Ankara—a concrete detail worth exploring. |

**Overall: 100.0% rule checks (53/53) · zero invented facts in 2/2 runs**
