#!/usr/bin/env bash
# Destroy everything setup_3services.sh created. Run after the demo is recorded.
set -uo pipefail
REGION=us-east-1
echo "== stop load loops"; rm -f /tmp/demo-ii-fulfillment-load /tmp/demo-ii-checkout-load 2>/dev/null || true
for p in $(pgrep -f "demo-ii-fulfillment-load\|demo-ii-checkout-load" 2>/dev/null); do kill "$p" 2>/dev/null || true; done
echo "== delete alarms"; aws cloudwatch delete-alarms --region $REGION \
  --alarm-names demo-ii-fulfillment-failures demo-ii-payments-backlog demo-ii-checkout-errors 2>/dev/null || true
echo "== delete Step Functions state machine"; SM=$(aws stepfunctions list-state-machines --region $REGION --query "stateMachines[?name=='demo-ii-fulfillment'].stateMachineArn" --output text 2>/dev/null); [ -n "$SM" ] && [ "$SM" != "None" ] && aws stepfunctions delete-state-machine --state-machine-arn "$SM" --region $REGION 2>/dev/null || true
echo "== delete SQS queue"; Q=$(aws sqs get-queue-url --queue-name demo-ii-payments --region $REGION --query QueueUrl --output text 2>/dev/null); [ -n "$Q" ] && [ "$Q" != "None" ] && aws sqs delete-queue --queue-url "$Q" --region $REGION 2>/dev/null || true
echo "== delete Lambda"; aws lambda delete-function --function-name demo-ii-checkout-api --region $REGION 2>/dev/null || true
echo "teardown done (roles demo-ii-lambda-role, demo-ii-sfn-role kept; delete manually if you want)"
