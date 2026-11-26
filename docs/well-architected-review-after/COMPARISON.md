# Before vs after: Well-Architected Security review of the Incident Investigator

> **Classification: CONFIDENTIAL**

**Before** = the earlier run, `../review/` (run 20261126T044842Z-h7q2). **After** = this run, `aws-well-architected-review-report.md` (run 20261126T083309Z-r7q2, tag v2-after, commit 46a5056).
Both runs used the real `aws-well-architected-review` skill, Security pillar, 52 of 52 BP pages read in full, 10 of 10 spot-checks passed, standard business criticality.

Order of work: the after run was finished and written first, without reading `../review/` or `target/docs/well-architected-review/` or `target/bench/`. The earlier report and ledger were read only after that, to write this file.

## What the earlier run reviewed, and what the fix changed

The earlier report says "5 commits", "no tests/ directory, no .github/ workflows". That is commit 38a21f0, the parent of the bench and test commits. Comparing 38a21f0 with v2-after (excluding bench/ and docs/well-architected-review/):

| File | Change |
|---|---|
| harness/investigate.py | +88/-11: trust boundary (`UNTRUSTED_KEYS`, `SAFE_ERROR_TYPES`, `trusted_view`), `neutralize`, `fallback_rca`, fail-closed `guard`, `nova_rca` prompt uses `trusted_view(ev)`, defanged log text in `post_issue` and `main` |
| docs/THREAT-MODEL.md | new, 24 lines |
| tests/test_security.py | new, 100 lines |
| .github/workflows/ci.yml | new, 14 lines |
| README.md | +7 lines (pointer to the hardening branch) |

Not touched by the fix: `gather_*` functions in investigate.py, `crons/investigator_job.py`, all of `infra/*.sh`, `.gitignore`, and the live AWS account state. The static IAM key, ReadOnlyAccess, alarms without actions, no scanning and no log retention are all in that untouched set.

## Headline numbers

| Measure | Before | After |
|---|---|---|
| Pillar score (agent judgment, not computed) | 2 of 5 | 3 of 5 |
| BP status (Implemented / Partially / Not Implemented / Not Applicable / Cannot Determine) | 3 / 22 / 7 / 11 / 9 | 1 / 25 / 8 / 10 / 8 |
| Gap rows (Partially or Not Implemented) | 29 (3 High, 14 Medium, 12 Low) | 33 (1 High, 14 Medium, 18 Low) |
| Findings by risk | 0 Critical, 3 High, 5 Medium, 3 Low (11) | 0 Critical, 1 High, 7 Medium, 11 Low (19) |
| BP rows with the same status and risk in both runs | 27 of 52 | 27 of 52 |
| BP rows that changed status or risk | 25 of 52 (21 status, 4 risk only) | |

Finding counts are not a clean comparison. The earlier run bundled 29 gap rows into 11 findings. This run bundled 33 gap rows into 19 findings and listed 11 Low items separately. Compare gap rows, not findings.

**What moved because of the fix:** the two High rows that were about untrusted input and unclassified data (SEC01-BP06, SEC07-BP01) both dropped to Medium. The one High row the fix did not target (SEC02-BP02, static IAM key) stayed High. That is the cleanest signal in the data: High gap rows 3 -> 1, and the 2 that fell are the 2 the fix aimed at.

**What did not move:** the overall status distribution got slightly worse (Implemented 3 -> 1, Not Implemented 7 -> 8, gap rows 29 -> 33). That is driven by rows in code the fix never touched (see the noise section). The score of 3 versus 2 is a judgment the agent writes in prose, so I would not call it a measured improvement on its own.

## Rows changed because of the fix (evidence is in code the fix added or changed)

| BP | Before | After | Why | Evidence (after run) |
|---|---|---|---|---|
| SEC01-BP06 Threat model | Not Implemented, High | Partially Implemented, Medium | A STRIDE model now exists with scope, trust rule, controls and residual risk. It still covers one data path, with no prioritization or owners. | docs/THREAT-MODEL.md:3-24 |
| SEC07-BP01 Data classification | Not Implemented, High | Partially Implemented, Medium | The model classifies values as trusted or untrusted by who can write them, and names secrets in log text as a disclosure risk. Caveat below. | docs/THREAT-MODEL.md:5-7,14 |
| SEC11-BP03 Automate testing | Not Implemented, Medium | Partially Implemented, Medium | pytest runs on every push and PR, with 15 security tests. No SAST, SCA or SBOM. | .github/workflows/ci.yml:2,14; tests/test_security.py |
| SEC01-BP02 Control objectives | Not Implemented, Medium | Partially Implemented, Low | Each STRIDE threat maps to a control and to evidence, and tests validate controls. Note: the earlier gap was "no check that the read-only claim holds"; the new tests do not test that claim. The upgrade comes from the threat-to-control mapping. | docs/THREAT-MODEL.md:9-16; tests/test_security.py |
| SEC01-BP05 Automate security controls | Partially Implemented, Medium | Partially Implemented, Low | A pipeline now exists. Controls are still applied by hand with CLI scripts. | .github/workflows/ci.yml:14; infra/setup_readonly.sh:13 |
| SEC01-BP03 Stay current on threats | Cannot Determine | Partially Implemented, Low | Weak effect: the threat model cites prompt injection and STRIDE. No feed or dependency updater exists. | docs/THREAT-MODEL.md:3-16 |
| SEC10-BP04 Run simulations | Cannot Determine | Partially Implemented, Low | New tests simulate hostile log text. The break/fix drills were cited by both runs. | tests/test_security.py:56-72; infra/incidents3.sh:10-67 |
| SEC11-BP08 Pipeline security | Not Applicable | Partially Implemented, Low | A pipeline now exists, so the BP applies. It has least-privilege permissions and no cloud credentials, but actions are pinned by tag, not SHA. This is a new, small gap created by adding CI. | .github/workflows/ci.yml:3-4,9,11 |

## The rows you asked about

**SEC01-BP06 (threat model):** Not Implemented High -> Partially Implemented Medium. Before: "exhaustive search of the repo for threat, STRIDE, risk, injection, untrusted: none", Impact Moderate, Likelihood High. After: docs/THREAT-MODEL.md:3-24, Impact Moderate, Likelihood Low. Genuine effect of the fix.

**SEC11-BP02 (secure coding guidelines):** Partially Implemented Medium in both runs. The label did not change, but the reasoning did. Before: untrusted log text reaches the Nova prompt and a GitHub issue (investigate.py:253, :291-298) and the guard checks only integers (:259-267), Impact Moderate, Likelihood Medium. After: the trust boundary, allowlist, `neutralize` and fail-closed guard are present (harness/investigate.py:249-333); the remaining gap is "no written standard or OWASP/CWE mapping, no SAST in CI", Impact Moderate, Likelihood Low. So the fix lowered the likelihood from Medium to Low, and the Medium-level label hides it. The BP asks for written guidelines and enforced scans, so a code fix alone does not move this row.

**Guard and untrusted input in other rows:**
- SEC07-BP02: Partially Implemented Medium in both runs. The model no longer sees workload free text (investigate.py:259-266) and output is defanged (:269-279), but secrets or PII in a log line are still printed and posted to a GitHub issue (:343, :383) with no redaction and no repo-visibility check. THREAT-MODEL.md:14,24 says redaction is still open. The review agrees: unchanged.
- SEC04-BP01: unchanged Partially Implemented Medium, same unmasked-sensitive-data anti-pattern.
- SEC07-BP03: Cannot Determine -> Not Implemented Low. The after run found no sensitive-data detection before posting. This is a stricter reading of the same unchanged posting path, not a fix effect.
- The earlier High finding "no threat model, untrusted log text flows to an LLM and a GitHub issue" (F-02) has no High counterpart in the after report. Untrusted text to the model appears only as Medium findings F-04 (no written standard or SAST) and F-07 (threat model scope).
- The earlier High finding F-03 "log data leaves the account unclassified and unredacted" became Medium F-02 (secrets or PII posted unredacted). Caveat: the downgrade of SEC07-BP01 reflects that the trust model now documents the data, not that less data leaves the account. The raw log line is still posted, only defanged.

## All 25 changed rows, classified

Class A = fix effect (above). Class B = ambiguous: the after evidence cites a file the fix added or changed, but the change in status is explained by something else. Class C = variance: both runs' evidence is in code or live state the fix did not touch.

| BP | Before | After | Class | Reason for the difference |
|---|---|---|---|---|
| SEC01-BP02 | NI Medium | PI Low | A | threat-to-control mapping, see above |
| SEC01-BP03 | CD | PI Low | A (weak) | threat model mentions threat classes |
| SEC01-BP04 | I | PI Low | C | after run notes the investigator host is self-managed (crons/investigator_job.py:8-22); same files before |
| SEC01-BP05 | PI Medium | PI Low | A | CI exists |
| SEC01-BP06 | NI High | PI Medium | A | threat model |
| SEC02-BP04 | PI Low | NI Medium | C | same IAM user evidence (infra/setup_readonly.sh:9-12); stricter label |
| SEC03-BP03 | PI Low | NI Low | C | both runs saw no Access Analyzer; different label |
| SEC05-BP02 | CD | NA | C | same fact (no security group in infra/*.sh); different label |
| SEC06-BP01 | PI Medium | NI Medium | B | after run read Inspector status live (DISABLED), which the earlier run did not; ci.yml has no scanner but that is not a regression |
| SEC06-BP02 | NA | CD | C | same fact (host image not in repo, crons/investigator_job.py:19) |
| SEC06-BP03 | I | PI Low | C | same scripts run by hand (infra/*.sh, README.md:132-157) |
| SEC06-BP04 | PI Low | NI Low | B | same unsigned Lambda zip (infra/setup_3services.sh:59-72); ci.yml:13 adds one more unpinned install |
| SEC06-BP05 | PI Low | NI Low | C | after run read Inspector and GuardDuty live (off); the earlier run did not assert live state |
| SEC07-BP01 | NI High | PI Medium | A | threat model, see above |
| SEC07-BP03 | CD | NI Low | B | same unchanged posting path (investigate.py:336-364), stricter label |
| SEC07-BP04 | PI Medium | PI Low | C | after run read live log retention and teardown script; better by one level |
| SEC08-BP02 | CD | PI Low | C | after run read the live trail (no KMS) and SQS defaults |
| SEC10-BP01 | NI Medium | CD | C | skill rule: an unmentioned practice is Cannot Determine; the earlier run used Not Implemented for the same absence |
| SEC10-BP02 | PI Medium | CD | C | same README text read two ways |
| SEC10-BP04 | CD | PI Low | A | hostile-log tests |
| SEC10-BP05 | PI Low | CD | B | the earlier run credited RCA issues as blameless records (investigate.py post_issue); the after run did not. The issue path is unchanged. |
| SEC11-BP03 | NI Medium | PI Medium | A | CI and tests |
| SEC11-BP06 | NI Low | NI Medium | B | README.md:127/134 cited by both; the after run also cites ci.yml:13 (a second unpinned install, added by the fix) and rated likelihood higher |
| SEC11-BP07 | PI Low | PI Medium | C | same scripts and clone-and-run (crons/investigator_job.py:19-22); higher risk label |
| SEC11-BP08 | NA | PI Low | A | CI exists |

Class totals: A 8, B 5, C 12.

## Run-to-run noise

Mechanical rule, applied the same way to all 52 rows: a row is "touched by the fix" if the after run's evidence cites a file the fix added (ci.yml, THREAT-MODEL.md, tests/) or a line range of investigate.py that the fix changed. That gives **23 touched rows and 29 untouched rows** (untouched means the evidence is in infra/*.sh, crons/, .gitignore, the `gather_*` functions, README text or live account state).

**Changed status or risk in untouched rows: 11 of 29 (38%)**: SEC02-BP04, SEC03-BP03, SEC05-BP02, SEC06-BP02, SEC06-BP03, SEC06-BP05, SEC07-BP04, SEC08-BP02, SEC10-BP01, SEC10-BP02, SEC11-BP07 (9 status changes, 2 risk-only: SEC07-BP04 and SEC11-BP07).
Changed in touched rows: 14 of 23 (61%). By judgment (table above), 8 of those 14 are real fix effects (Class A) and 5 are ambiguous (Class B); the 14th, SEC01-BP04, is Class C because it cites the Bedrock call lines but its change comes from the host being self-managed. So by judgment: **12 Class C rows are variance (11 mechanical + SEC01-BP04), 5 Class B rows are probably variance too, 8 Class A rows are fix effects.** The estimate of noise is therefore 11 to 17 changed rows out of 25, and the number I would quote is 11 of 29 untouched rows (38%).

Direction of the 11 untouched-row changes: worse 5 (SEC02-BP04, SEC03-BP03, SEC06-BP05 to Not Implemented; SEC06-BP03 Implemented to Partially; SEC11-BP07 risk up), better 2 (SEC07-BP04 risk down, SEC08-BP02 Cannot Determine to Partially), relabels 4 (SEC05-BP02, SEC06-BP02, SEC10-BP01, SEC10-BP02).

Why they differ: the after run made more live reads (Inspector, GuardDuty, log-group retention, MFA devices, access key list) and applied the skill's rule that Not Implemented needs explicit negative evidence while an unmentioned practice is Cannot Determine. The earlier run ran `simulate-principal-policy`, which this run did not. Risk pairs also differ for the same row (SEC02-BP02 was Impact Moderate, Likelihood High before and Impact Severe, Likelihood Medium after; both are High). One pair of runs is one sample, so 38% is an estimate, not a rate.

## Rows that did not change

27 of 52. Notable ones: SEC02-BP02 Not Implemented High (static key, the fix did not touch it), SEC02-BP03, SEC02-BP05, SEC03-BP01, SEC04-BP01, SEC04-BP02, SEC07-BP02, SEC11-BP02, SEC11-BP01/04/05 (Cannot Determine), SEC09-BP02 Implemented, and the Not Applicable network and key-management rows.
Full list: SEC01-BP01, SEC01-BP07, SEC02-BP01, SEC02-BP02, SEC02-BP03, SEC02-BP05, SEC03-BP01, SEC03-BP02, SEC03-BP04, SEC03-BP05, SEC04-BP01, SEC04-BP02, SEC05-BP01, SEC05-BP03, SEC05-BP04, SEC07-BP02, SEC08-BP01, SEC08-BP03, SEC08-BP04, SEC09-BP01, SEC09-BP02, SEC09-BP03, SEC10-BP03, SEC11-BP01, SEC11-BP02, SEC11-BP04, SEC11-BP05.

## What got worse

- Gap rows 29 -> 33, Low gap rows 12 -> 18, Implemented rows 3 -> 1, Not Implemented rows 7 -> 8.
- Caused or partly caused by the fix: SEC11-BP08 (a new CI file creates a new Low gap: actions pinned by tag), SEC11-BP06 (CI adds a second unpinned `pip install boto3 pytest`, and the risk rose from Low to Medium; README.md:134 was already cited before), SEC06-BP04 (same unpinned install). All three are small and are consequences of adding CI without dependency pinning or scanning.
- Not caused by the fix: SEC01-BP04, SEC02-BP04, SEC03-BP03, SEC06-BP03, SEC06-BP05, SEC11-BP07, SEC10-BP02 (variance or more live evidence, see above). SEC06-BP01, SEC07-BP03 and SEC10-BP05 are Class B: they cite fix files but the change comes from live reads or a stricter label.
- No new Critical or High finding. The fix code introduced no gap that this Security review flagged against `trusted_view`, `neutralize`, `guard` or `fallback_rca`.

## Limits on what this comparison shows

- The skill reads code and documents and makes live read-only calls. It did not run the tests, the guard or the benchmark, so it cannot confirm the README's "12/40 steered RCAs to 0/40" figures. This run read tests/test_security.py but did not execute it.
- The rows that moved most (SEC01-BP06, SEC07-BP01, SEC11-BP03, SEC01-BP02, SEC01-BP05, SEC11-BP08) moved because of the new threat model, tests and CI file. The guard code itself appears in the evidence of SEC11-BP02, SEC07-BP02 and SEC04-BP01, and those rows kept their labels. The skill rewards written artifacts and pipelines more than a code-level fix.
- This run read README.md:19-24 and docs/THREAT-MODEL.md, which mention the earlier review and its finding numbers. They are in the permitted scope. No status was taken from their claims; each row cites code, scripts, tests or live reads.
