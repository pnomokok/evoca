# Chat agent evaluation

Chat model: `us.amazon.nova-2-lite-v1:0` (temperature 0.3) · judge model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (temperature 0) · simulated person: `us.amazon.nova-2-lite-v1:0` · runs per scenario: 2

Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used `us.amazon.nova-pro-v1:0`), so the judge columns (invented facts, follow-ups, declined topic, warmth) are not directly comparable with it.

| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | Declined topic respected | Warmth | Avg turn (ms) | Note |
|---|---|---|---|---|---|---|---|
| many_relatives | 60/62 | 2/2 | 2/2 | – | 5.0 | 1301 | Companion could have gently encouraged more detail about the mother question before accepting the decline. Failed: relation_before_Aylin ×1, relation_before_Defne ×1 |

**Overall: 96.8% rule checks (60/62) · zero invented facts in 2/2 runs**
