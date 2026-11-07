#!/usr/bin/env bash
# Plant a real, read-only-investigable AWS incident: an "orders API" Lambda whose timeout was
# cut from 10s to 1s, so every call times out and the Errors alarm fires. Idempotent.
# All resources are prefixed demo-ii- so reset.sh can delete exactly them.
set -euo pipefail
REGION=us-east-1
FN=demo-ii-orders-api
ALARM=demo-ii-orders-errors
ROLE=demo-ii-lambda-role
ACCT=$(aws sts get-caller-identity --query Account --output text)

echo "== execution role"
if ! aws iam get-role --role-name $ROLE >/dev/null 2>&1; then
  aws iam create-role --role-name $ROLE --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name $ROLE --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 10
fi
ROLE_ARN=arn:aws:iam::$ACCT:role/$ROLE

echo "== function code (sleeps ~2s, so a 1s timeout fails and a 10s timeout passes)"
tmp=$(mktemp -d); cat > "$tmp/handler.py" <<'PY'
import json, time
def lambda_handler(event, context):
    # the orders API does ~2 seconds of real work
    time.sleep(2)
    order_id = (event or {}).get("order_id", "unknown")
    return {"statusCode": 200, "body": json.dumps({"ok": True, "order_id": order_id})}
PY
( cd "$tmp" && zip -q fn.zip handler.py )

echo "== create or reset the function to the GOOD config (timeout 10)"
if aws lambda get-function --function-name $FN --region $REGION >/dev/null 2>&1; then
  aws lambda update-function-code --function-name $FN --zip-file "fileb://$tmp/fn.zip" --region $REGION >/dev/null
  aws lambda wait function-updated --function-name $FN --region $REGION
  aws lambda update-function-configuration --function-name $FN --timeout 10 --region $REGION >/dev/null
else
  aws lambda create-function --function-name $FN --runtime python3.12 --role "$ROLE_ARN" \
    --handler handler.lambda_handler --timeout 10 --memory-size 128 \
    --zip-file "fileb://$tmp/fn.zip" --region $REGION >/dev/null
fi
aws lambda wait function-updated --function-name $FN --region $REGION
rm -rf "$tmp"

echo "== alarm on Errors"
aws cloudwatch put-metric-alarm --alarm-name $ALARM --region $REGION \
  --alarm-description "demo-ii orders API errors" \
  --namespace AWS/Lambda --metric-name Errors --statistic Sum --period 60 \
  --evaluation-periods 1 --threshold 0 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching \
  --dimensions Name=FunctionName,Value=$FN >/dev/null

echo "== confirm GOOD state: invoke once, expect 200"
aws lambda invoke --function-name $FN --payload '{"order_id":"A-1001"}' --cli-binary-format raw-in-base64-out /tmp/ii_out.json --region $REGION >/dev/null
echo "   good invoke -> $(cat /tmp/ii_out.json | head -c 80)"
echo "setup done: $FN (timeout 10, healthy), alarm $ALARM"
