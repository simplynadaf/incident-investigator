# Threat model (STRIDE), written for Well-Architected finding F-02

Scope: the path **monitored workload -> CloudWatch / Step Functions -> investigator -> Amazon Nova Pro -> GitHub issue -> on-call human**.

Trust rule: a value is **trusted** only if changing it needs AWS write permissions on the control plane (alarm state, metrics, function
configuration, CloudTrail events, the queue's counters). Text that the *monitored workload itself* can write is **untrusted**: log lines
and Step Functions execution causes. Anyone who can make an application log `ERROR ...` controls up to 170 characters of it.

| STRIDE | Threat on this path | Control (this change) | Evidence |
|---|---|---|---|
| **S**poofing | A log line imitates the investigator, an on-call note or a "SYSTEM" instruction | Untrusted text is shown only inside a labelled, defanged log line. It never enters the model prompt. | `bench/results-after.json`, `tests/test_security.py` |
| **T**ampering | Attacker text steers the RCA toward a fake cause or a fake fix | `trusted_view()` drops free text; the prompt carries trusted evidence and one constrained error type | 12 of 40 steered RCAs before, 0 of 40 after |
| **R**epudiation | A reader cannot tell which part of an issue is application text | The issue labels the log line "application text, untrusted, defanged"; the RCA is the guard's output | `post_issue()` |
| **I**nformation disclosure | Secrets in log text reach Bedrock and a GitHub issue | Out of scope for this change. Tracked as review finding F-03 (redaction, private-repo check). | `docs/well-architected-review/` |
| **D**enial of service | A flood of hostile log lines wastes model calls | Not changed. Cost is bounded by one Converse call per investigation. | n/a |
| **E**levation of privilege | A human or tool follows an attacker's "fix" (`curl ... \| sh`) | Fail-closed guard: a command, URL, address or key in the answer replaces the whole answer with a deterministic RCA built from trusted evidence | `guard()`, 5 fabricated outputs rejected 5/5 |

## Residual risk (honest)

- The error type is the one thing taken from untrusted text. It must match a fixed allowlist of Python exception names, so it cannot carry a sentence.
- The guard checks numbers, times, identifiers, ARNs, URLs, addresses, keys, commands and "by <name>". A model could still write a false statement
  that uses none of those. That is why the model no longer sees the application text at all.
- A Step Functions `Error` name is shown only through the defanged log line; the model does not see it.
- Redaction of secrets before data leaves the account (F-03) and the long-term access key (F-01) are still open.
