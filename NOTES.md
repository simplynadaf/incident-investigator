# Incident Investigator: running notes
- Story (one sentence):
- Constraints from the user:
- Research results (success rates, sample sizes):
- Claims to verify:
- Decisions and why:
- Failures hit and fixes:

## Research findings (confirmed live)
- Account 175662053988, user/server. Read-only AWS access confirmed.
- Incident chain all reachable read-only:
  - Alarm demo-ii-orders-errors (Errors > 0).
  - Metric AWS/Lambda Errors on demo-ii-orders-api (3+ datapoints after the bad change).
  - Logs: "Task timed out after 1.00 seconds" (instant source).
  - Invoke error: Sandbox.Timedout, "Task timed out after 1.00 seconds".
  - CloudTrail lookup-events works WITHOUT a trail (90-day history). BUT management events lag 5-15 min.
- ROOT CAUSE planted: timeout cut 10 -> 1 via UpdateFunctionConfiguration. Function GetFunctionConfiguration
  returns Timeout=1 and LastModified instantly, so "what changed + when" is authoritative from Lambda itself.

## Decisions
- "What changed" evidence = Lambda GetFunctionConfiguration (Timeout + LastModified), INSTANT and authoritative.
  CloudTrail UpdateFunctionConfiguration is CORROBORATION (who did it), shown when it has caught up.
- To avoid CloudTrail lag on camera: plant the incident ~15-20 min before the live take so CloudTrail
  populates. The "live" part is the agent INVESTIGATING an already-fired alarm (honest: it finds root
  cause in ~60s, the change does not need to be < 60s old).
- Deliverable: agent posts the RCA as a GitHub issue on simplynadaf/incident-investigator (read-only to
  AWS; writes only a GitHub issue to my own repo). Prints the report in the terminal too.
- Read-only safety: investigator runs under a read-only identity; a write attempt shows AccessDenied on camera.
- Honest: no fabricated MTTR. Show the real wall-clock of the run. State it finds THIS class of incident;
  novel ones still need a human.

## Final build (all verified)
- investigator: harness/investigate.py. 4/4 rehearsals correct. Runs in 1-3s. Read-only AWS + bedrock:InvokeModel only.
- Identity demo-ii-readonly: ReadOnlyAccess + a tight bedrock:InvokeModel on nova-pro ONLY. Proven:
  - CAN read the alarm; CANNOT update the Lambda (AccessDeniedException). This is the on-camera safety beat.
  - Bedrock inference is additive and does NOT let it touch any infrastructure. Honest framing: "read-only on your
    infra; it only calls a model to phrase what it found."
- Deliverable: RCA posted as a GitHub issue on simplynadaf/incident-investigator (issue #1 is a rehearsal; reset deletes/reopens).
- Evidence chain: alarm -> Errors metric spike -> CloudWatch Logs "Status: timeout" -> Lambda GetFunctionConfiguration
  (Timeout=1, authoritative) -> CloudTrail UpdateFunctionConfiguration (who/when, corroboration).
- Honest numbers for the video: investigator found this root cause in every rehearsal (deterministic evidence; only the
  phrasing varies, bounded by the guard). It finds THIS class (config/timeout). Novel incidents still need a human.
  No fabricated MTTR; show the real wall-clock (~2s).

## FOUR incident use cases, all tested (clean sweep passed)
One read-only investigator, four distinct failure modes, correct root cause each time:
1. TIMEOUT    config change (timeout 10->1)            evidence: "Status: timeout" log + Timeout=1
2. CODE BUG   bad deploy (KeyError 'order')            evidence: "[ERROR] KeyError" + new code
3. MEMORY     config change (OOM at 128MB)             evidence: "[ERROR] MemoryError" + memory=128
4. THROTTLE   reserved concurrency = 0                 evidence: Throttles metric + reservedConc=0 (no error log)
Key reliability fix: anchor the log window to the function's LastModified (the incident's own change) so a
previous incident's log line is never picked up. Signal priority: throttle (no log) checked before log-based kinds.
infra/incidents.sh {timeout|codebug|memory|throttle|heal}. Throttle uses a second alarm demo-ii-orders-throttles.
Video plan: show 3 incidents live (timeout, code bug, memory or throttle) to prove it generalizes; one read-only
safety beat; honest limits (it finds these classes; novel incidents need a human; real wall-clock, no MTTR claim).
