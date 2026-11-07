#!/usr/bin/env bash
# Cause the incident, ON CAMERA this is done by a deployer identity, not the investigator.
# Cuts the timeout 10 -> 1 (UpdateFunctionConfiguration, logged by CloudTrail) and drives a few
# invocations so they time out and the Errors alarm fires.
set -euo pipefail
REGION=us-east-1; FN=demo-ii-orders-api
echo "== BAD change: timeout 10 -> 1 (this is the planted root cause)"
aws lambda update-function-configuration --function-name $FN --timeout 1 --region $REGION >/dev/null
aws lambda wait function-updated --function-name $FN --region $REGION
echo "== drive traffic so it times out"
for i in 1 2 3 4 5; do
  aws lambda invoke --function-name $FN --payload "{\"order_id\":\"A-10$i\"}" --cli-binary-format raw-in-base64-out /tmp/ii_bad.json --region $REGION >/dev/null 2>&1 || true
done
echo "== recent log line:"; sleep 6
aws logs filter-log-events --log-group-name /aws/lambda/$FN --region $REGION --filter-pattern "Task timed out" --max-items 1 --query 'events[].message' --output text 2>&1 | head -c 140; echo
echo "incident live. The alarm will flip to ALARM within ~1-2 minutes."
