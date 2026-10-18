# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 1

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| grandmother_basic | 29/29 | 1/1 | 1/1 | – | 4.0 | 1449 | Companion offered to replay stories without confirming they were actually recorded, creating a false expectation. |
| many_relatives | 30/31 | 1/1 | 1/1 | – | 5.0 | 3220 | Companion could have offered to return to Defne's wedding question or Aylin's question about her mother at a future session. Failed: relation_before_Defne ×1 |

**Overall: 98.3% rule checks (59/60) · zero invented facts in 2/2 runs**
