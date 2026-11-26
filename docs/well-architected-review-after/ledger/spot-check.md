> **Classification: CONFIDENTIAL**

# Spot-check - run 20261126T083309Z-r7q2

Fixed sample: the first BP of S01 and of the shards at positions ceil(i x 13 / 10) for i = 2..10 (S03, S04, S06, S07, S08, S10, S11, S12, S13). No web_fetch rows, no page_unreadable rows. All 10 pages re-read with aws___read_documentation (max_length 30000, truncated false).

| BP ID | shard | outcome quote found | tail quote found | total_length row / now | pass |
|---|---|---|---|---|---|
| SEC01-BP05 | S01 | yes | yes | 7072 / 7072 | pass |
| SEC11-BP05 | S03 | yes | yes | 5346 / 5346 | pass |
| SEC02-BP01 | S04 | yes | yes | 8083 / 8083 | pass |
| SEC04-BP01 | S06 | yes | yes | 8573 / 8573 | pass |
| SEC10-BP01 | S07 | yes | yes | 7524 / 7524 | pass |
| SEC01-BP01 | S08 | yes | yes | 6678 / 6678 | pass |
| SEC06-BP01 | S10 | yes | yes | 8018 / 8018 | pass |
| SEC07-BP01 | S11 | yes | yes | 5454 / 5454 | pass |
| SEC08-BP01 | S12 | yes | yes | 6610 / 6610 | pass |
| SEC09-BP01 | S13 | yes | yes | 7871 / 7871 | pass |

Totals: 10 sampled, 10 passed, 0 unreadable lines, 0 shards redone. Agent-checked, not machine-verified. The sample is fixed by the shard plan and confirms the sampled quotes are on the page, not every row.
