#!/usr/bin/env python3
"""Cost of the fix: Nova latency, prompt size and guard fallback rate on the 3 honest incidents.
Run on both commits:  python3 bench/timing.py --label before|after --n 10"""
import argparse, json, statistics, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import investigate as inv
ap = argparse.ArgumentParser(); ap.add_argument("--label"); ap.add_argument("--n", type=int, default=10); a = ap.parse_args()
lat, fb, size = [], 0, []
orig = inv.boto3.client
class Spy:
    def __init__(s, c): s.c = c
    def converse(s, **kw):
        size.append(len(kw["messages"][0]["content"][0]["text"])); return s.c.converse(**kw)
inv.boto3.client = lambda *x, **k: Spy(orig(*x, **k))
for k in ("checkout", "payments", "fulfillment"):
    ev = json.loads((ROOT / "bench/evidence" / f"honest_{k}.json").read_text())
    for _ in range(a.n):
        t = time.time(); raw = inv.nova_rca(ev); lat.append(time.time() - t)
        final, stripped = inv.guard(raw, ev); fb += int(final != raw)
r = {"label": a.label, "runs": len(lat), "nova_p50_s": round(statistics.median(lat), 2), "nova_p95_s": round(sorted(lat)[int(.95*len(lat))-1], 2),
     "prompt_chars_mean": round(statistics.mean(size)), "answers_replaced_by_fallback": fb}
print(json.dumps(r)); Path(ROOT / "bench" / f"timing-{a.label}.json").write_text(json.dumps(r, indent=1))
