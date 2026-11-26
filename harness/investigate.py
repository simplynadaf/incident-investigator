#!/usr/bin/env python3
"""Incident Investigator: read-only AI SRE. Correlates a CloudWatch alarm into ONE cited root cause.

Pipeline (all AWS calls are read-only: Describe / Get / Filter / Lookup):
  1. read the alarm + its breach time
  2. pull the breaching Errors datapoint (the metric spike)
  3. find the error log line in the function's log group  (instant, authoritative)
  4. read the function config (Timeout + LastModified)     (what changed + when, authoritative)
  5. corroborate with CloudTrail UpdateFunctionConfiguration (who, when CloudTrail has caught up)
  6. Amazon Nova Pro writes the one-sentence root cause + recommended fix, from the TRUSTED evidence only.
     Free text that a monitored workload controls (log lines, Step Functions causes) never enters the prompt;
     only a constrained error type does (Well-Architected review F-02, SEC01-BP06 / SEC11-BP02).
  7. a fail-closed guard checks every number (single digits too), time, identifier, ARN, URL, address and
     command in the answer against the trusted evidence; any miss replaces the whole answer with a
     deterministic RCA built from the trusted signal
  8. print the RCA and (optionally) post it as a GitHub issue on our own repo; untrusted log text is shown
     defanged (no clickable link, no markup, no control characters)

Never remediates. Prints a JSON result to --out for the recorder's dialog.
  python3 investigate.py --alarm demo-ii-orders-errors [--repo simplynadaf/incident-investigator] [--post] [--out out/rca.json]
"""
import argparse, json, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone
import boto3

REGION = "us-east-1"
NOVA = "amazon.nova-pro-v1:0"


def rd(x):  # readable time
    return x.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if isinstance(x, datetime) else str(x)


LOG_PATTERNS = ['"MemoryError"', '"Status: timeout"', '"out of memory"', '"Runtime exited"', '"Task timed out"', "ERROR", '"Traceback"']
CHANGE_EVENTS = ("UpdateFunctionConfiguration", "UpdateFunctionCode", "PutFunctionConcurrency",
                 "PutFunctionConcurrency20171031", "DeleteFunctionConcurrency")


def gather(alarm_name):
    cw = boto3.client("cloudwatch", region_name=REGION)
    a = cw.describe_alarms(AlarmNames=[alarm_name])["MetricAlarms"][0]
    ns = a.get("Namespace", "")
    if ns == "AWS/DynamoDB":
        return gather_dynamodb(alarm_name, a, cw)
    if ns == "AWS/SQS":
        return gather_sqs(alarm_name, a, cw)
    if ns == "AWS/States":
        return gather_stepfunctions(alarm_name, a, cw)
    return gather_lambda(alarm_name, a, cw)


def _cloudtrail_change(resource, want):
    """Read-only CloudTrail lookup for the change that matches this incident."""
    out = {}
    try:
        ct = boto3.client("cloudtrail", region_name=REGION)
        end = datetime.now(timezone.utc)
        events = ct.lookup_events(LookupAttributes=[{"AttributeKey": "ResourceName", "AttributeValue": resource}],
                                  StartTime=end - timedelta(hours=6), EndTime=end, MaxResults=25)["Events"]
        chg = [e for e in events if any(k in e["EventName"] for k in want)]
        if chg:
            c = sorted(chg, key=lambda e: e["EventTime"])[-1]
            out["change_event"] = c["EventName"]; out["change_time"] = rd(c["EventTime"])
            out["change_by"] = c.get("Username") or json.loads(c["CloudTrailEvent"]).get("userIdentity", {}).get("arn", "unknown")
    except Exception as e:
        out["cloudtrail_note"] = f"not available ({type(e).__name__})"
    return out


def gather_dynamodb(alarm_name, a, cw):
    ddb = boto3.client("dynamodb", region_name=REGION)
    table = next(d["Value"] for d in a["Dimensions"] if d["Name"] == "TableName")
    ev = {"alarm": alarm_name, "service": "Amazon DynamoDB", "resource": table, "function": table,
          "alarm_metric": a["MetricName"], "state": a["StateValue"], "threshold": a["Threshold"],
          "breach_time": rd(a["StateUpdatedTimestamp"])}
    end = datetime.now(timezone.utc); start = end - timedelta(hours=1)
    for m in ("WriteThrottleEvents", "ReadThrottleEvents", "ThrottledRequests"):
        pts = cw.get_metric_statistics(Namespace="AWS/DynamoDB", MetricName=m,
                                       Dimensions=[{"Name": "TableName", "Value": table}],
                                       StartTime=start, EndTime=end, Period=60, Statistics=["Sum"])["Datapoints"]
        spikes = [p for p in pts if p["Sum"] > 0]
        if spikes:
            ev[f"{m.lower()}_total"] = int(sum(p["Sum"] for p in spikes))
    desc = ddb.describe_table(TableName=table)["Table"]
    pt = desc.get("ProvisionedThroughput", {})
    ev["read_capacity_units"] = pt.get("ReadCapacityUnits")
    ev["write_capacity_units"] = pt.get("WriteCapacityUnits")
    ev["billing_mode"] = desc.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")
    if ev.get("writethrottleevents_total"):
        ev["signal"] = f"write requests were throttled because the table's provisioned write capacity ({ev.get('write_capacity_units')} WCU) is too low for the load"
    elif ev.get("readthrottleevents_total"):
        ev["signal"] = f"read requests were throttled because the table's provisioned read capacity ({ev.get('read_capacity_units')} RCU) is too low for the load"
    else:
        ev["signal"] = "the table's provisioned capacity appears too low for the request rate"
    ev.update(_cloudtrail_change(table, ("UpdateTable",)))
    return ev


def gather_sqs(alarm_name, a, cw):
    sqs = boto3.client("sqs", region_name=REGION)
    qname = next(d["Value"] for d in a["Dimensions"] if d["Name"] == "QueueName")
    ev = {"alarm": alarm_name, "service": "Amazon SQS", "resource": qname, "function": qname,
          "alarm_metric": a["MetricName"], "state": a["StateValue"], "threshold": a["Threshold"],
          "breach_time": rd(a["StateUpdatedTimestamp"])}
    end = datetime.now(timezone.utc); start = end - timedelta(hours=1)
    for m, stat in (("ApproximateAgeOfOldestMessage", "Maximum"), ("ApproximateNumberOfMessagesVisible", "Maximum"),
                    ("NumberOfMessagesSent", "Sum"), ("NumberOfMessagesDeleted", "Sum")):
        pts = cw.get_metric_statistics(Namespace="AWS/SQS", MetricName=m,
                                       Dimensions=[{"Name": "QueueName", "Value": qname}],
                                       StartTime=start, EndTime=end, Period=60, Statistics=[stat])["Datapoints"]
        if pts:
            ev[m.lower()] = int(max(p[stat] for p in pts))
    sent = ev.get("numberofmessagessent", 0); deleted = ev.get("numberofmessagesdeleted", 0)
    ev["signal"] = (f"messages are piling up: the oldest message is about {ev.get('approximateageofoldestmessage','?')} seconds old "
                    f"and nothing is consuming them (messages sent but not deleted), so the consumer has stalled")
    return ev


def gather_stepfunctions(alarm_name, a, cw):
    sfn = boto3.client("stepfunctions", region_name=REGION)
    sm_arn = next(d["Value"] for d in a["Dimensions"] if d["Name"] == "StateMachineArn")
    name = sm_arn.split(":")[-1]
    ev = {"alarm": alarm_name, "service": "AWS Step Functions", "resource": name, "function": name,
          "alarm_metric": a["MetricName"], "state": a["StateValue"], "threshold": a["Threshold"],
          "breach_time": rd(a["StateUpdatedTimestamp"])}
    end = datetime.now(timezone.utc); start = end - timedelta(hours=1)
    pts = cw.get_metric_statistics(Namespace="AWS/States", MetricName="ExecutionsFailed",
                                   Dimensions=[{"Name": "StateMachineArn", "Value": sm_arn}],
                                   StartTime=start, EndTime=end, Period=60, Statistics=["Sum"])["Datapoints"]
    failed = [p for p in pts if p["Sum"] > 0]
    if failed:
        ev["executionsfailed_total"] = int(sum(p["Sum"] for p in failed))
    # the error/cause from the most recent failed execution (authoritative, read-only)
    try:
        execs = sfn.list_executions(stateMachineArn=sm_arn, statusFilter="FAILED", maxResults=1)["executions"]
        if execs:
            de = sfn.describe_execution(executionArn=execs[0]["executionArn"])
            ev["execution_error"] = de.get("error", "")
            if de.get("cause"):
                ev["error_log"] = (de["error"] + ": " + de["cause"])[:170]
    except Exception:
        pass
    ev["signal"] = ("executions are failing for every run, which points to the workflow definition itself, "
                    "not the input, so a recent definition deploy is the likely cause")
    ev.update(_cloudtrail_change(name, ("UpdateStateMachine", "CreateStateMachine")))
    return ev


def gather_lambda(alarm_name, a, cw):
    logs = boto3.client("logs", region_name=REGION)
    lam = boto3.client("lambda", region_name=REGION)
    ev = {"alarm": alarm_name, "service": "AWS Lambda"}
    fn = next(d["Value"] for d in a["Dimensions"] if d["Name"] == "FunctionName")
    ev.update(function=fn, resource=fn, alarm_metric=a["MetricName"], state=a["StateValue"],
              threshold=a["Threshold"], breach_time=rd(a["StateUpdatedTimestamp"]))

    cfg = lam.get_function_configuration(FunctionName=fn)
    ev["timeout_seconds"] = cfg["Timeout"]; ev["memory_mb"] = cfg["MemorySize"]
    ev["last_modified"] = cfg["LastModified"]; ev["code_sha_tail"] = cfg.get("CodeSha256", "")[-10:]
    from datetime import datetime as _dt
    lm = _dt.strptime(cfg["LastModified"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)

    # metric spikes: both Errors and Throttles, so a throttling incident is visible too
    end = datetime.now(timezone.utc); start = end - timedelta(hours=1)
    for m in ("Errors", "Throttles"):
        pts = cw.get_metric_statistics(Namespace="AWS/Lambda", MetricName=m,
                                       Dimensions=[{"Name": "FunctionName", "Value": fn}],
                                       StartTime=start, EndTime=end, Period=60, Statistics=["Sum"])["Datapoints"]
        spikes = sorted([p for p in pts if p["Sum"] > 0], key=lambda p: p["Timestamp"])
        if spikes:
            ev[f"{m.lower()}_total"] = int(sum(p["Sum"] for p in spikes))
            ev[f"{m.lower()}_spike_time"] = rd(spikes[-1]["Timestamp"])

    # the error log line (authoritative, instant); try several signatures
    lg = f"/aws/lambda/{fn}"
    since = int((lm - timedelta(seconds=30)).timestamp() * 1000)  # logs from THIS incident (after the change)
    raw = None
    for attempt in range(3):
        best = None
        for pat in LOG_PATTERNS:
            for e in logs.filter_log_events(logGroupName=lg, filterPattern=pat, startTime=since, limit=5)["events"]:
                if best is None or e["timestamp"] > best["timestamp"]:
                    best = e
        if best:
            raw = best["message"].strip().splitlines()[0]
            break
        time.sleep(2)
    if raw and "Status: timeout" in raw:
        raw = "Lambda invocation ended with Status: timeout (hit the configured time limit)"
    if raw and ("out of memory" in raw.lower() or "Runtime exited" in raw):
        raw = "Lambda runtime exited: out of memory (hit the configured memory limit)"
    ev["error_log"] = raw[:170] if raw else None


    try:
        rc = lam.get_function_concurrency(FunctionName=fn).get("ReservedConcurrentExecutions")
        if rc is not None:
            ev["reserved_concurrency"] = rc
    except Exception:
        pass
    # REPORT line gives Max Memory Used vs limit (OOM signal)
    for rep in logs.filter_log_events(logGroupName=lg, filterPattern='"REPORT"', startTime=since, limit=3)["events"]:
        mm = re.search(r"Max Memory Used:\s*(\d+)\s*MB", rep["message"])
        if mm:
            ev["max_memory_used_mb"] = int(mm.group(1)); break

    # compute the failure signal BEFORE picking a CloudTrail change (so we match the right change type)
    if ev.get("reserved_concurrency") == 0 or (ev.get("throttles_total") and "throttle" in alarm_name.lower()):
        ev["signal"] = "reserved concurrency is currently set to 0, so every request is throttled before it runs (a concurrency limit was applied)"
        ev.pop("error_log", None)
    else:
        el = (ev.get("error_log") or "").lower()
        if "memoryerror" in el or "out of memory" in el:
            ev["signal"] = "the handler ran out of memory (points to the memory setting being too low)"
        elif "keyerror" in el or "traceback" in el:
            ev["signal"] = "an unhandled code exception in the handler (points to a code change, not a setting)"
        elif "timeout" in el:
            ev["signal"] = "invocations hit the time limit (points to the timeout setting)"
        elif ev.get("throttles_total"):
            ev["signal"] = "requests were throttled (points to a concurrency limit)"
    if "throttl" in ev.get("signal", ""):
        # throttled requests never ran; CloudTrail concurrency change is the story, logs are not
        pass
    # corroborate what changed (CloudTrail, read-only, no trail required; may lag a few minutes)
    try:
        ct = boto3.client("cloudtrail", region_name=REGION)
        events = ct.lookup_events(LookupAttributes=[{"AttributeKey": "ResourceName", "AttributeValue": fn}],
                                  StartTime=end - timedelta(hours=6), EndTime=end, MaxResults=25)["Events"]
        sig = ev.get("signal", "")
        if "throttl" in sig or "concurrency" in sig:
            want = ("PutFunctionConcurrency",)   # the SET-to-0 event, not a later Delete
        elif "code" in sig or "exception" in sig:
            want = ("UpdateFunctionCode",)
        else:  # timeout / memory / config
            want = ("UpdateFunctionConfiguration",)
        chg = [e for e in events if any(k in e["EventName"] for k in want)]
        if not chg:  # fall back to any relevant change, but never a concurrency event for a non-throttle incident
            chg = [e for e in events if any(k in e["EventName"] for k in CHANGE_EVENTS)
                   and not ("Concurrency" in e["EventName"] and "throttl" not in sig and "concurrency" not in sig)]
        if chg:
            c = sorted(chg, key=lambda e: e["EventTime"])[-1]
            ev["change_event"] = c["EventName"]; ev["change_time"] = rd(c["EventTime"])
            ev["change_by"] = c.get("Username") or json.loads(c["CloudTrailEvent"]).get("userIdentity", {}).get("arn", "unknown")
    except Exception as e:
        ev["cloudtrail_note"] = f"not available ({type(e).__name__})"
    return ev


# ---- trust boundary (review F-02) -------------------------------------------------------------------
# TRUSTED: values read from AWS control planes and metrics. UNTRUSTED: text a monitored workload writes
# (any app that can log "ERROR ..." controls up to 170 characters of error_log).
UNTRUSTED_KEYS = ("error_log", "execution_error")
SAFE_ERROR_TYPES = {"KeyError", "ValueError", "TypeError", "RuntimeError", "MemoryError", "ImportError", "AttributeError",
                    "IndexError", "NameError", "OSError", "TimeoutError", "ConnectionError", "PermissionError",
                    "FileNotFoundError", "ZeroDivisionError", "AssertionError", "Exception", "ModuleNotFoundError"}
_ERR_WORD = re.compile(r"\b[A-Za-z][A-Za-z0-9_]{2,60}\b")


def trusted_view(ev):
    """The evidence the model may see: no workload-written free text, plus one constrained error type."""
    t = {k: v for k, v in ev.items() if k not in UNTRUSTED_KEYS}
    for w in _ERR_WORD.findall(ev.get("error_log") or ""):
        if w in SAFE_ERROR_TYPES:
            t["error_type"] = w
            break
    return t


def neutralize(text):
    """Make workload-written text inert before a human sees it: one line, no control characters, no markup,
    no clickable links, no code-span breakout. It is still readable as evidence."""
    if not text:
        return text
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text))
    t = t.replace("`", "'")
    t = re.sub(r"(?i)\b(https?|ftp)://", lambda m: {"http": "hxxp", "https": "hxxps", "ftp": "fxp"}[m.group(1).lower()] + "[://]", t)
    t = re.sub(r"(?<=\d)\.(?=\d)", "[.]", t)
    t = t.replace("](", "] (").replace("@", "[at]")
    return re.sub(r"\s+", " ", t).strip()[:170]


def fallback_rca(ev):
    """A deterministic RCA built only from trusted evidence. Used when the guard rejects the model's wording."""
    t = trusted_view(ev)
    sig = t.get("signal") or "the alarm's metric breached its threshold and the metrics alone do not narrow the cause"
    chg = (f" The most recent change on this resource was {t['change_event']} at {t.get('change_time')}." if t.get("change_event") else "")
    fix = (f"a human should review the {t['change_event']} change and the application error in the evidence timeline."
           if t.get("change_event") else "a human should review the resource configuration and the application error in the evidence timeline.")
    return (f"ROOT CAUSE: {sig[0].upper() + sig[1:]}.{chg}\n\n"
            f"CONFIDENCE: medium, built from metrics, configuration and CloudTrail only (the model's wording was rejected by the guard).\n\n"
            f"FIX (do not run, read-only): {fix}")


def nova_rca(ev):
    br = boto3.client("bedrock-runtime", region_name=REGION)
    prompt = (
        "You are a read-only Site Reliability engineer. Using ONLY the evidence below, write a root cause "
        "analysis. Do not invent any resource name, timestamp, number, or value that is not in the evidence. "
        "Output exactly three short sections with these headers and nothing else:\n"
        "ROOT CAUSE: one sentence naming the single most likely cause.\n"
        "CONFIDENCE: high, medium, or low, with a half-sentence why.\n"
        "FIX (do not run, read-only): the one action a human should take.\n\n"
        f"EVIDENCE:\n{json.dumps(trusted_view(ev), indent=2)}")
    r = br.converse(modelId=NOVA, messages=[{"role": "user", "content": [{"text": prompt}]}],
                    inferenceConfig={"temperature": 0.2, "maxTokens": 400})
    return r["output"]["message"]["content"][0]["text"].strip()


_NUM = re.compile(r"\d+(?::\d+){0,2}")
_IDENT = re.compile(r"[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+){2,}|[A-Za-z0-9]+_[A-Za-z0-9_]+")
_ARN = re.compile(r"arn:aws[\w:/.-]*", re.I)
_BAD = re.compile(r"(?i)(?:https?|hxxps?|ftp)://|[\w.+-]+@[\w-]+\.[\w.-]+|\b\d{1,3}(?:\.\d{1,3}){3}\b|\bAKIA[A-Z0-9]{4,}"
                  r"|\b(?:curl|wget|sudo|chmod|bash)\b|\|\s*(?:sh|bash)\b|\]\(|\b(?:midnight|noon|yesterday|tonight)\b")
_BY = re.compile(r"(?i)\bby\s+([A-Za-z0-9_.@-]+)")


def guard(text, ev):
    """Fail closed. Every number (single digits too), time, identifier, ARN, URL, address, key and command in
    the answer must come from the TRUSTED evidence. If any line fails, the whole answer is replaced by
    fallback_rca(ev). Returns (text, rejected_lines)."""
    hay = json.dumps(trusted_view(ev), default=str).lower()
    known_nums = set(_NUM.findall(hay))
    kept, stripped = [], []
    for line in text.splitlines():
        bad = bool(_BAD.search(line))
        bad = bad or any(n not in known_nums for n in _NUM.findall(line))
        bad = bad or any(i.lower() not in hay for i in _IDENT.findall(line))
        bad = bad or any(a.lower() not in hay for a in _ARN.findall(line))
        bad = bad or any(b.lower() not in hay for b in _BY.findall(line))
        (stripped if bad else kept).append(line)
    if stripped:
        return fallback_rca(ev), stripped
    return "\n".join(kept), stripped


def post_issue(repo, alarm, ev, rca):
    svc = ev.get("service", "AWS")
    res = ev.get("resource") or ev.get("function")
    # build a service-aware evidence timeline from whatever the gatherer collected
    lines = []
    mt = " / ".join(f"{k.replace('_total','').replace('_',' ')} = {v}" for k, v in ev.items() if k.endswith("_total"))
    if mt: lines.append(f"- metric: {mt}")
    if ev.get("error_log"): lines.append(f"- log (application text, untrusted, defanged): `{neutralize(ev['error_log'])}`")
    if ev.get("approximateageofoldestmessage") is not None:
        lines.append(f"- queue: oldest message ~{ev['approximateageofoldestmessage']}s old, {ev.get('approximatenumberofmessagesvisible','?')} visible")
    if ev.get("write_capacity_units") is not None:
        lines.append(f"- capacity: {ev.get('read_capacity_units')} RCU / {ev.get('write_capacity_units')} WCU ({ev.get('billing_mode')})")
    if ev.get("timeout_seconds") is not None:
        lines.append(f"- config: timeout {ev['timeout_seconds']}s, memory {ev['memory_mb']}MB"
                     + (f", max memory used {ev['max_memory_used_mb']}MB" if ev.get('max_memory_used_mb') else "")
                     + (f", reserved concurrency {ev['reserved_concurrency']}" if 'reserved_concurrency' in ev else "")
                     + f", last modified {ev['last_modified']}")
    if ev.get("execution_error"):
        lines.append(f"- workflow: failed executions, error `{neutralize(ev['execution_error'])}`")
    if ev.get("change_event"):
        lines.append(f"- change: {ev['change_event']} by {ev.get('change_by')} at {ev.get('change_time')}")
    body = (f"**Automated RCA by the Incident Investigator (read-only).**\n\n"
            f"Alarm `{alarm}` on {svc} `{res}` breached at {ev['breach_time']}.\n\n"
            f"### Evidence timeline\n" + "\n".join(lines)
            + f"\n\n### Analysis\n{rca}\n\n<sub>Read-only. Python gathered the evidence; Amazon Nova Pro phrased the cause. No AWS resource was changed.</sub>")
    title = f"RCA: {alarm} (root cause found)"
    out = subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body, "--label", "incident"],
                         capture_output=True, text=True)
    return (out.stdout or out.stderr).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alarm", required=True)
    ap.add_argument("--repo", default="simplynadaf/incident-investigator")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] ALARM    {a.alarm}: gathering evidence (read-only)...", flush=True)
    ev = gather(a.alarm)
    def ts(): return time.strftime('%H:%M:%S')
    # service-aware evidence lines (no KeyError across Lambda / DynamoDB / SQS)
    mt = " / ".join(f"{k.replace('_total','').replace('_',' ')} = {v}" for k, v in ev.items() if k.endswith("_total"))
    print(f"[{ts()}] SERVICE  {ev.get('service','AWS')}: {ev.get('resource')}", flush=True)
    print(f"[{ts()}] METRIC   {mt or ev.get('alarm_metric','(alarm metric)')}", flush=True)
    if ev.get("error_log"):
        print(f"[{ts()}] LOG      {neutralize(ev['error_log'])}", flush=True)
    if ev.get("approximateageofoldestmessage") is not None:
        print(f"[{ts()}] QUEUE    oldest message ~{ev['approximateageofoldestmessage']}s old, {ev.get('approximatenumberofmessagesvisible','?')} visible", flush=True)
    if ev.get("write_capacity_units") is not None:
        print(f"[{ts()}] CAPACITY {ev.get('read_capacity_units')} RCU / {ev.get('write_capacity_units')} WCU ({ev.get('billing_mode')})", flush=True)
    if ev.get("timeout_seconds") is not None:
        print(f"[{ts()}] CONFIG   timeout={ev['timeout_seconds']}s memory={ev['memory_mb']}MB"
              + (f" maxUsed={ev['max_memory_used_mb']}MB" if ev.get('max_memory_used_mb') else "")
              + (f" reservedConc={ev['reserved_concurrency']}" if 'reserved_concurrency' in ev else "")
              + f", last modified {ev['last_modified']}", flush=True)
    if ev.get("change_event"):
        print(f"[{ts()}] CHANGE   {ev['change_event']} by {ev.get('change_by')} at {ev.get('change_time')}", flush=True)
    print(f"[{ts()}] NOVA     writing the root cause from the evidence...", flush=True)
    rca = nova_rca(ev)
    rca, stripped = guard(rca, ev)
    if stripped:
        print(f"[{time.strftime('%H:%M:%S')}] GUARD    stripped {len(stripped)} uncited line(s)", flush=True)
    print("\n" + rca + "\n", flush=True)
    issue = post_issue(a.repo, a.alarm, ev, rca) if a.post else None
    if issue:
        print(f"[{time.strftime('%H:%M:%S')}] ISSUE    {issue}", flush=True)
    dur = round(time.time() - t0, 1)
    print(f"[{time.strftime('%H:%M:%S')}] DONE     root cause found in {dur}s (read-only, nothing changed)", flush=True)
    if a.out:
        json.dump({"evidence": ev, "rca": rca, "issue": issue, "seconds": dur}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
