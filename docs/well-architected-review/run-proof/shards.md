Order: workload-first, S01-S07 focus shards, then the rest in manifest order
S01 | security | SEC02 | SEC02-BP01 SEC02-BP02 SEC02-BP03 SEC02-BP04 SEC02-BP05 | focus: identity, long-lived key, secrets
S02 | security | SEC03 | SEC03-BP01 SEC03-BP02 SEC03-BP03 SEC03-BP04 SEC03-BP05 | focus: ReadOnlyAccess, least privilege
S03 | security | SEC04 | SEC04-BP01 SEC04-BP02 | focus: logging, alarms
S04 | security | SEC11 | SEC11-BP01 SEC11-BP02 SEC11-BP03 SEC11-BP04 | focus: application code
S05 | security | SEC11 | SEC11-BP05 SEC11-BP06 SEC11-BP07 SEC11-BP08 | focus: code review, deploy, pipeline
S06 | security | SEC09 | SEC09-BP01 SEC09-BP02 SEC09-BP03 | focus: Bedrock and GitHub calls
S07 | security | SEC10 | SEC10-BP01 SEC10-BP02 SEC10-BP03 SEC10-BP04 SEC10-BP05 | focus: incident tooling
S08 | security | SEC01 | SEC01-BP01 SEC01-BP02 SEC01-BP03 SEC01-BP04 | rest
S09 | security | SEC01 | SEC01-BP05 SEC01-BP06 SEC01-BP07 | rest
S10 | security | SEC05 | SEC05-BP01 SEC05-BP02 SEC05-BP03 SEC05-BP04 | rest
S11 | security | SEC06 | SEC06-BP01 SEC06-BP02 SEC06-BP03 SEC06-BP04 SEC06-BP05 | rest
S12 | security | SEC07 | SEC07-BP01 SEC07-BP02 SEC07-BP03 SEC07-BP04 | rest
S13 | security | SEC08 | SEC08-BP01 SEC08-BP02 SEC08-BP03 SEC08-BP04 | rest
