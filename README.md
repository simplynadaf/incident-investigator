<div align="center">

# 🔍 Incident Investigator: a read-only AI SRE

### A CloudWatch alarm fires. In about a minute, this agent traces it from the alarm, to the metric spike, to the exact error log line, to the change that caused it, and names one cited root cause. It runs read-only: it investigates and recommends, it never remediates. The analysis is posted straight to a GitHub issue.

[![Amazon Nova Pro](https://img.shields.io/badge/Agent-Amazon%20Nova%20Pro-FF9900?logo=amazon&logoColor=white)](https://aws.amazon.com/bedrock/nova/)
[![Kiro Crew](https://img.shields.io/badge/Runs%20as-a%20Kiro%20Crew%20job-8b5cf6)](https://kiro.dev)
[![Read only](https://img.shields.io/badge/Read%20only-cannot%20remediate-2fd27a)](#-read-only-by-design)
[![No LLM judge](https://img.shields.io/badge/Python%20gathers%20the%20evidence-38bdf8)](#-how-it-works)
[![License: MIT](https://img.shields.io/badge/License-MIT-8b5cf6)](LICENSE)

> Most AI for incidents makes you faster at correlating signals, not at isolating the cause. This one commits to a single root cause with a confidence level, and tells you what it could not verify.

</div>

---

## 🤔 What it does

An alarm tells you something is wrong, not why. A human SRE then opens five tabs: the alarm, the metric, the logs, the function config, the deploy history. The Incident Investigator does that walk for you, read-only, and returns one cited root cause plus the fix a human should run.

It works across different failure classes, not one trick. In the demo it solves three in a row:

| Incident | What broke | Root cause it found |
|---|---|---|
| ⏱️ Timeout | the function timeout was cut from 10s to 1s | "timeout set to 1 second, too low" (a config change) |
| 🐞 Code bug | a bad deploy throws a KeyError | "a code deploy introduced an unhandled KeyError" |
| 🚦 Throttle | reserved concurrency set to 0 | "reserved concurrency set to 0, every request throttled" |

The third has no error log at all, because throttled requests never run. The agent reads the Throttles metric and the concurrency limit instead, and still names the real cause.

---

## 🧠 How it works

```
 🚨  A CloudWatch alarm on a Lambda function
       │
       ▼
 🔎  read-only evidence (boto3: Describe / Get / Filter / Lookup)
       │   alarm -> Errors or Throttles spike -> the error log line
       │   -> GetFunctionConfiguration (timeout, memory, concurrency, last modified)
       │   -> CloudTrail: the change that matches the failure (config / code / concurrency)
       ▼
 ✍️  Amazon Nova Pro writes ONE root cause + a confidence level + the fix
       │   using only the evidence; a guard strips any number the evidence lacks
       ▼
 📋  posted as a GitHub issue (read-only to AWS; writes only an issue to your repo)
```

- **`harness/investigate.py`** gathers the evidence and calls Nova Pro. Read-only to AWS.
- **`infra/incidents.sh`** plants each demo incident (`timeout | codebug | memory | throttle | heal`).
- **`infra/setup_readonly.sh`** creates the read-only identity and proves a write is denied.
- **`crons/investigator_job.py`** runs it as a Kiro Crew job (the job message is its config).

---

## 🔒 Read-only by design

The agent runs under an identity with `ReadOnlyAccess` plus one narrow permission: `bedrock:InvokeModel` on the Nova model, so it can phrase what it found. It has no permission to change any AWS resource. A write attempt returns `AccessDeniedException`, on camera. It investigates; a human decides and acts.

---

## 🚀 Run it

```bash
git clone https://github.com/simplynadaf/incident-investigator ~/incident-investigator
cd ~/incident-investigator
python3.11 -m venv .venv && .venv/bin/pip install boto3

# plant a demo incident, then investigate it read-only
bash infra/setup_incident.sh          # a healthy orders-API Lambda + an Errors alarm
bash infra/incidents.sh timeout       # break it (cuts the timeout to 1s)
AWS_PROFILE=ii-readonly python3 harness/investigate.py --alarm demo-ii-orders-errors --post
bash infra/incidents.sh heal          # put it back
```

Requirements: AWS credentials, a read-only profile (`infra/setup_readonly.sh`), `gh` logged in, and Bedrock access to `amazon.nova-pro-v1:0` in us-east-1.

---

## 🧾 Honest limits

- It finds common classes: a config change, a bad deploy, a starved function, a throttle. A novel, first-of-its-kind outage still needs a human.
- Every value it reports comes from your telemetry. The guard strips any number the evidence does not contain.
- It reports the real wall-clock of each run. It does not claim an MTTR figure.
- The incident set here is small and deliberately clean, to make the demo reproducible.

---

## 📝 License

MIT. See [LICENSE](LICENSE).

---

<div align="center">

**Sarvar Nadaf** · Cloud Architect · AI Infrastructure & DevOps

[Portfolio](https://sarvarnadaf.com) · [GitHub](https://github.com/simplynadaf) · [LinkedIn](https://www.linkedin.com/in/sarvar04/) · [YouTube](https://www.youtube.com/@sarvar-nadaf)

*The agent investigates. A human decides. Nothing gets remediated by a model.*

</div>
