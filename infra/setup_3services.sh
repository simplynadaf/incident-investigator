#!/usr/bin/env bash
# Provision a small, realistic 3-service system for the Incident Investigator demo:
#   1) Step Functions  demo-ii-fulfillment  (bad-deploy incident: a failing definition)
#   2) SQS queue        demo-ii-payments     (backlog incident: oldest message ages out)
#   3) Lambda function  demo-ii-checkout-api (timeout incident: config change 10s -> 1s)
# Each has its own CloudWatch alarm. All resources are prefixed demo-ii- so teardown is exact.
# Idempotent. Provision -> record -> run teardown_3services.sh.
set -uo pipefail
REGION=us-east-1
ACCT=$(aws sts get-caller-identity --query Account --output text)
ROLE=demo-ii-lambda-role

echo "== [role] lambda execution role"
if ! aws iam get-role --role-name $ROLE >/dev/null 2>&1; then
  aws iam create-role --role-name $ROLE --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name $ROLE --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 10
fi
ROLE_ARN=arn:aws:iam::$ACCT:role/$ROLE

# ---------- 1) Step Functions: demo-ii-fulfillment (healthy = Pass/succeeds) ----------
echo "== [stepfunctions] state machine demo-ii-fulfillment"
SFNROLE=demo-ii-sfn-role
if ! aws iam get-role --role-name $SFNROLE >/dev/null 2>&1; then
  aws iam create-role --role-name $SFNROLE --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"states.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  sleep 8
fi
SFN_ROLE_ARN=arn:aws:iam::$ACCT:role/$SFNROLE
GOOD='{"Comment":"fulfillment","StartAt":"Fulfill","States":{"Fulfill":{"Type":"Pass","Result":{"ok":true},"End":true}}}'
SM_ARN=$(aws stepfunctions list-state-machines --region $REGION --query "stateMachines[?name=='demo-ii-fulfillment'].stateMachineArn" --output text)
if [ -z "$SM_ARN" ] || [ "$SM_ARN" = "None" ]; then
  SM_ARN=$(aws stepfunctions create-state-machine --name demo-ii-fulfillment --role-arn "$SFN_ROLE_ARN" --definition "$GOOD" --region $REGION --query stateMachineArn --output text)
else
  aws stepfunctions update-state-machine --state-machine-arn "$SM_ARN" --definition "$GOOD" --region $REGION >/dev/null
fi
aws cloudwatch put-metric-alarm --alarm-name demo-ii-fulfillment-failures --region $REGION \
  --alarm-description "demo-ii fulfillment workflow failed executions" \
  --namespace AWS/States --metric-name ExecutionsFailed --statistic Sum --period 60 \
  --evaluation-periods 1 --threshold 0 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching --dimensions Name=StateMachineArn,Value="$SM_ARN" >/dev/null

# ---------- 2) SQS: demo-ii-payments ----------
echo "== [sqs] queue demo-ii-payments"
QURL=$(aws sqs get-queue-url --queue-name demo-ii-payments --region $REGION --query QueueUrl --output text 2>/dev/null)
if [ -z "$QURL" ] || [ "$QURL" = "None" ]; then
  QURL=$(aws sqs create-queue --queue-name demo-ii-payments --region $REGION --query QueueUrl --output text)
  sleep 2
fi
aws cloudwatch put-metric-alarm --alarm-name demo-ii-payments-backlog --region $REGION \
  --alarm-description "demo-ii payments queue oldest message age" \
  --namespace AWS/SQS --metric-name ApproximateAgeOfOldestMessage --statistic Maximum --period 60 \
  --evaluation-periods 1 --threshold 60 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching --dimensions Name=QueueName,Value=demo-ii-payments >/dev/null

# ---------- 3) Lambda: demo-ii-checkout-api (sleeps ~2s; 1s timeout fails, 10s passes) ----------
echo "== [lambda] function demo-ii-checkout-api"
tmp=$(mktemp -d); cat > "$tmp/handler.py" <<'PY'
import json, time
def lambda_handler(event, context):
    time.sleep(2)  # the checkout API does ~2 seconds of real work
    return {"statusCode": 200, "body": json.dumps({"ok": True, "cart": (event or {}).get("cart", "unknown")})}
PY
( cd "$tmp" && zip -q fn.zip handler.py )
if aws lambda get-function --function-name demo-ii-checkout-api --region $REGION >/dev/null 2>&1; then
  aws lambda update-function-code --function-name demo-ii-checkout-api --zip-file "fileb://$tmp/fn.zip" --region $REGION >/dev/null
  aws lambda wait function-updated --function-name demo-ii-checkout-api --region $REGION
  aws lambda update-function-configuration --function-name demo-ii-checkout-api --timeout 10 --region $REGION >/dev/null
else
  aws lambda create-function --function-name demo-ii-checkout-api --runtime python3.12 --role "$ROLE_ARN" \
    --handler handler.lambda_handler --timeout 10 --memory-size 128 --zip-file "fileb://$tmp/fn.zip" --region $REGION >/dev/null
fi
aws lambda wait function-updated --function-name demo-ii-checkout-api --region $REGION
rm -rf "$tmp"
aws cloudwatch put-metric-alarm --alarm-name demo-ii-checkout-errors --region $REGION \
  --alarm-description "demo-ii checkout API errors" \
  --namespace AWS/Lambda --metric-name Errors --statistic Sum --period 60 \
  --evaluation-periods 1 --threshold 0 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching --dimensions Name=FunctionName,Value=demo-ii-checkout-api >/dev/null

echo "== healthy: a quick write + invoke"
aws lambda invoke --function-name demo-ii-checkout-api --payload '{"cart":"OK"}' --cli-binary-format raw-in-base64-out /tmp/ii_ck.json --region $REGION >/dev/null 2>&1 || true
echo "setup done: Step Functions demo-ii-fulfillment, SQS demo-ii-payments, Lambda demo-ii-checkout-api (+3 alarms)"
