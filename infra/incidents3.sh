#!/usr/bin/env bash
# Break or fix one of the 3 demo services, independently. Usage:
#   incidents3.sh break fulfillment|payments|checkout
#   incidents3.sh fix   fulfillment|payments|checkout
# Each break causes a real, read-only-investigable incident and trips that service's alarm.
set -uo pipefail
REGION=us-east-1
ACT=${1:-}; SVC=${2:-}

case "$ACT:$SVC" in
  # ---- Step Functions bad deploy: push a failing definition, drive executions in background ----
  break:fulfillment)
    echo "cause: Step Functions demo-ii-fulfillment bad definition deployed (executions fail)"
    SM=$(aws stepfunctions list-state-machines --region $REGION --query "stateMachines[?name=='demo-ii-fulfillment'].stateMachineArn" --output text)
    BAD='{"Comment":"fulfillment","StartAt":"Fulfill","States":{"Fulfill":{"Type":"Fail","Error":"PaymentServiceUnavailable","Cause":"downstream payment call failed"}}}'
    aws stepfunctions update-state-machine --state-machine-arn "$SM" --definition "$BAD" --region $REGION >/dev/null; sleep 3
    for i in 1 2 3 4 5; do aws stepfunctions start-execution --state-machine-arn "$SM" --input "{\"order\":\"F-$i\"}" --region $REGION >/dev/null 2>&1; done
    touch /tmp/demo-ii-fulfillment-load
    nohup bash -c 'SM="'"$SM"'"; while [ -f /tmp/demo-ii-fulfillment-load ]; do
      for i in 1 2 3; do aws stepfunctions start-execution --state-machine-arn "$SM" --input "{\"order\":\"L-$i\"}" --region '"$REGION"' >/dev/null 2>&1; done
      sleep 12; done' >/dev/null 2>&1 &
    echo "failing executions driven; ExecutionsFailed stays breached until fixed" ;;
  fix:fulfillment)
    echo "fix: roll the Step Functions definition back to the working version"
    rm -f /tmp/demo-ii-fulfillment-load
    for p in $(pgrep -f "demo-ii-fulfillment-load"); do kill "$p" 2>/dev/null; done
    sleep 3   # let any in-flight execution batch finish before restoring
    SM=$(aws stepfunctions list-state-machines --region $REGION --query "stateMachines[?name=='demo-ii-fulfillment'].stateMachineArn" --output text)
    GOOD='{"Comment":"fulfillment","StartAt":"Fulfill","States":{"Fulfill":{"Type":"Pass","Result":{"ok":true},"End":true}}}'
    aws stepfunctions update-state-machine --state-machine-arn "$SM" --definition "$GOOD" --region $REGION >/dev/null; sleep 3
    aws stepfunctions start-execution --state-machine-arn "$SM" --input '{"order":"OK"}' --region $REGION >/dev/null 2>&1
    echo "definition rolled back, executions succeed" ;;

  # ---- SQS backlog: push messages, leave them unconsumed so oldest ages past 60s ----
  break:payments)
    echo "cause: SQS demo-ii-payments backlog (consumer stalled, messages pile up)"
    Q=$(aws sqs get-queue-url --queue-name demo-ii-payments --region $REGION --query QueueUrl --output text)
    for i in $(seq 1 10); do aws sqs send-message --queue-url "$Q" --region $REGION \
      --message-body "{\"payment_id\":\"P-$i\"}" >/dev/null 2>&1 || true; done
    echo "10 payments queued, nothing is draining them; oldest will age out" ;;
  fix:payments)
    echo "fix: drain the backlog (the consumer is restarted)"
    Q=$(aws sqs get-queue-url --queue-name demo-ii-payments --region $REGION --query QueueUrl --output text)
    aws sqs purge-queue --queue-url "$Q" --region $REGION >/dev/null 2>&1 || true
    echo "queue drained" ;;

  # ---- Lambda timeout: cut timeout 10 -> 1, drive traffic in the background so it STAYS red ----
  break:checkout)
    echo "cause: Lambda demo-ii-checkout-api timeout cut 10 -> 1 (config change)"
    aws lambda update-function-configuration --function-name demo-ii-checkout-api --timeout 1 --region $REGION >/dev/null
    aws lambda wait function-updated --function-name demo-ii-checkout-api --region $REGION
    for i in 1 2 3 4 5 6; do aws lambda invoke --function-name demo-ii-checkout-api \
      --payload "{\"cart\":\"C-$i\"}" --cli-binary-format raw-in-base64-out /tmp/ii_c.json --region $REGION >/dev/null 2>&1 || true; done
    # keep traffic flowing in the BACKGROUND so the Errors alarm STAYS red until fixed
    nohup bash -c 'while [ -f /tmp/demo-ii-checkout-load ]; do
      for i in 1 2 3; do aws lambda invoke --function-name demo-ii-checkout-api \
        --payload "{\"cart\":\"L-$i\"}" --cli-binary-format raw-in-base64-out /tmp/ii_cl.json --region '"$REGION"' >/dev/null 2>&1; done
      sleep 10; done' >/dev/null 2>&1 &
    touch /tmp/demo-ii-checkout-load
    echo "calls timing out, background traffic keeps Errors breached until fixed" ;;
  fix:checkout)
    echo "fix: restore Lambda timeout to 10s (and stop the load)"
    rm -f /tmp/demo-ii-checkout-load
    aws lambda update-function-configuration --function-name demo-ii-checkout-api --timeout 10 --region $REGION >/dev/null
    aws lambda wait function-updated --function-name demo-ii-checkout-api --region $REGION
    aws lambda invoke --function-name demo-ii-checkout-api --payload '{"cart":"OK"}' --cli-binary-format raw-in-base64-out /tmp/ii_c.json --region $REGION >/dev/null 2>&1 || true
    echo "timeout restored, call returns 200" ;;

  *) echo "usage: incidents3.sh break|fix fulfillment|payments|checkout"; exit 1 ;;
esac
