# Spot-check - run 20261126T044842Z-h7q2 - CONFIDENTIAL
Fixed sample: first BP of S01 and of shards at positions ceil(i x 13 / 10) for i = 2..10 (S03, S04, S06, S07, S08, S10, S11, S12, S13). All ten pages were re-read with aws___read_documentation (max_length 30000, truncated false). No web_fetch rows and no page_unreadable rows exist, so none were added. Checked by the reviewing agent against the re-read text, not machine-verified.

| BP ID | shard | outcome quote found | tail quote found | total_length row / now | pass |
|---|---|---|---|---|---|
| SEC02-BP01 | S01 | yes | yes | 8083 / 8083 | pass |
| SEC04-BP01 | S03 | yes | yes (antipattern also found) | 8573 / 8573 | pass |
| SEC11-BP01 | S04 | yes | yes | 7217 / 7217 | pass |
| SEC09-BP01 | S06 | yes | yes | 7871 / 7871 | pass |
| SEC10-BP01 | S07 | yes | yes (antipattern also found) | 7524 / 7524 | pass |
| SEC01-BP01 | S08 | yes | yes (antipattern also found) | 6678 / 6678 | pass |
| SEC05-BP01 | S10 | yes | yes | 6716 / 6716 | pass |
| SEC06-BP01 | S11 | yes | yes | 8018 / 8018 | pass |
| SEC07-BP01 | S12 | yes | yes (antipattern also found) | 5454 / 5454 | pass |
| SEC08-BP01 | S13 | yes | yes | 6610 / 6610 | pass |

Totals: 10 sampled, 10 passed, 0 shards redone, 0 unreadable lines.
