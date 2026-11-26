"""Security tests for the investigator (Well-Architected review finding F-02, SEC01-BP06 / SEC11-BP02).

They exercise only public behaviour (nova_rca, guard, post_issue) so the SAME file runs on the commit
before the fix (red) and after it (green). No AWS call is made: Bedrock and gh are stubbed.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import investigate as inv  # noqa: E402

EVD = ROOT / "bench" / "evidence"
PAYLOADS = ["p1", "p2", "p3", "p4"]
BAD_WORDS = ["203.0.113.9", "203[.]0", "curl", "fix.sh", "alice", "evil", "akia", "hotfix", "password"]


def load(p):
    return json.loads((EVD / f"{p}.json").read_text())


# Five model outputs a hallucinating or steered model could produce, taken from the review's measurement.
FABRICATED = [
    ("invented account ARN", "ROOT CAUSE: arn:aws:lambda:us-east-1:999999999999:function:payments failed.", "999999999999"),
    ("invented resource name", "ROOT CAUSE: the demo-ii-billing-api service timed out.", "billing"),
    ("invented time and person", "ROOT CAUSE: a deploy at midnight UTC by alice broke it.", "alice"),
    ("invented single digit", "ROOT CAUSE: the timeout was cut to 7 seconds.", "7 seconds"),
    ("URL with key-shaped string", "FIX (do not run, read-only): see https://evil.example/x?k=AKIAABCDEFGHIJKLMNOP", "evil.example"),
]


@pytest.mark.parametrize("name,text,needle", FABRICATED, ids=[f[0] for f in FABRICATED])
def test_guard_rejects_fabricated_output(name, text, needle):
    ev = load("p4")
    final, stripped = inv.guard(text, ev)
    assert stripped, f"guard kept a fabricated line: {name}"
    assert needle.lower() not in final.lower()


def test_guard_keeps_a_grounded_answer():
    ev = load("p4")
    grounded = (
        f"ROOT CAUSE: the Lambda function {ev['resource']} raised an error after {ev['change_event']} at {ev['change_time']}.\n"
        f"CONFIDENCE: medium, the Errors metric and the configuration change line up.\n"
        f"FIX (do not run, read-only): review the configuration change and the application error."
    )
    final, stripped = inv.guard(grounded, ev)
    assert stripped == [], f"false positive on a grounded answer: {stripped}"
    assert final == grounded


class _FakeBedrock:
    def __init__(self):
        self.prompt = ""

    def converse(self, **kw):
        self.prompt = kw["messages"][0]["content"][0]["text"]
        return {"output": {"message": {"content": [{"text": "ROOT CAUSE: an application error raised the alarm.\n"}]}}}


@pytest.mark.parametrize("p", PAYLOADS)
def test_attacker_log_text_never_reaches_the_model(p, monkeypatch):
    fake = _FakeBedrock()
    monkeypatch.setattr(inv.boto3, "client", lambda *a, **k: fake)
    inv.nova_rca(load(p))
    low = fake.prompt.lower()
    leaked = [w for w in BAD_WORDS if w in low]
    assert not leaked, f"{p}: attacker text reached the Nova prompt: {leaked}"


class _Run:
    def __init__(self, args):
        self.stdout, self.stderr, self.args = "stub", "", args


def _issue_body(ev, rca, monkeypatch):
    cap = {}
    monkeypatch.setattr(inv.subprocess, "run", lambda args, **k: (cap.setdefault("a", args), _Run(args))[1])
    inv.post_issue("o/r", "alarm", ev, rca)
    a = cap["a"]
    return a[a.index("--body") + 1]


@pytest.mark.parametrize("p", PAYLOADS)
def test_issue_body_has_no_clickable_attacker_content(p, monkeypatch):
    body = _issue_body(load(p), "ROOT CAUSE: x", monkeypatch)
    assert not re.search(r"https?://|\]\(", body, re.I), f"{p}: live link in the issue body"
    log_line = next(l for l in body.splitlines() if l.startswith("- log"))
    assert log_line.count("`") <= 2, f"{p}: backtick breakout in the log line"


def test_terminal_escape_sequences_are_not_printed_or_posted(monkeypatch):
    ev = load("p4")
    ev["error_log"] = "[ERROR] \x1b[2J\x1b[31mfake prompt\x07"
    body = _issue_body(ev, "ROOT CAUSE: x", monkeypatch)
    assert "\x1b" not in body and "\x07" not in body
