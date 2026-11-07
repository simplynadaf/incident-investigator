"""Kiro Crew script job: run the read-only Incident Investigator on an alarm.
ctx.message is JSON config: {"alarm": "demo-ii-orders-errors"} or {"alarm": "...", "post": true}.
Runs under the read-only profile (AWS_PROFILE=ii-readonly) and appends to work/investigator.log.
"""
import json, os, subprocess
from pathlib import Path

HOME = Path(os.environ.get("II_HOME", Path.home() / "incident-investigator"))
LOG = HOME / "work" / "investigator.log"


def run(ctx):
    cfg = {}
    try:
        cfg = json.loads(ctx.message) if getattr(ctx, "message", None) else {}
    except Exception:
        pass
    alarm = cfg.get("alarm", "demo-ii-orders-errors")
    argv = [str(HOME / ".venv/bin/python") if (HOME / ".venv/bin/python").exists() else "python3",
            str(HOME / "harness/investigate.py"), "--alarm", alarm,
            "--repo", cfg.get("repo", "simplynadaf/incident-investigator"),
            "--out", str(HOME / "work" / "rca.json")]
    if cfg.get("post"):
        argv.append("--post")
    env = dict(os.environ, AWS_PROFILE="ii-readonly")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"\n===== investigate {json.dumps(cfg)} =====\n"); f.flush()
        p = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=180)
        out = (p.stdout + p.stderr)
        for line in out.splitlines():
            if "DeprecationWarning" in line or "boto3/compat" in line or line.strip().startswith("warnings.warn"):
                continue
            f.write(line + "\n")
        f.flush()
    try:
        ctx.notify(f"Incident Investigator ran on {alarm}")
    except Exception:
        pass
    return "done"
