#!/usr/bin/env bash
# Four distinct, read-only-investigable incidents on the same orders-API Lambda, plus a healer.
# usage: incidents.sh {timeout|codebug|memory|throttle|heal}
# Each cause makes the Errors (or Throttles) alarm fire; the investigator must name the right root cause.
set -euo pipefail
REGION=us-east-1; FN=demo-ii-orders-api; ALARM=demo-ii-orders-errors; TALARM=demo-ii-orders-throttles
CMD=${1:?timeout|codebug|memory|throttle|heal}

good_code() { cat <<'PY'
import json, time
def lambda_handler(event, context):
    time.sleep(2)                          # the orders API does ~2s of real work
    order_id = (event or {}).get("order_id", "unknown")
    return {"statusCode": 200, "body": json.dumps({"ok": True, "order_id": order_id})}
PY
}
bad_code() { cat <<'PY'
import json
def lambda_handler(event, context):
    # bad deploy: reads the wrong payload shape, throws KeyError on every real request
    order_id = event["order"]["id"]        # KeyError: 'order'
    return {"statusCode": 200, "body": json.dumps({"ok": True, "order_id": order_id})}
PY
}
mem_code() { cat <<'PY'
import json
def lambda_handler(event, context):
    blob = bytearray(260 * 1024 * 1024)    # allocate ~260MB; OOMs under a 128MB limit
    return {"statusCode": 200, "body": json.dumps({"ok": True, "n": len(blob)})}
PY
}
deploy() { local f=$(mktemp -d); eval "$1" > "$f/handler.py"; ( cd "$f" && zip -q c.zip handler.py )
  aws lambda update-function-code --function-name $FN --zip-file "fileb://$f/c.zip" --region $REGION >/dev/null
  aws lambda wait function-updated --function-name $FN --region $REGION; rm -rf "$f"; }
drive() { for i in $(seq 1 ${1:-5}); do aws lambda invoke --function-name $FN --payload "{\"order_id\":\"A-$RANDOM\"}" \
  --cli-binary-format raw-in-base64-out /tmp/ii_d.json --region $REGION >/dev/null 2>&1 || true; done; }

case "$CMD" in
  timeout)
    echo "cause: config change, timeout 10 -> 1 (no code change)"
    aws lambda update-function-configuration --function-name $FN --timeout 1 --memory-size 128 --region $REGION >/dev/null
    aws lambda wait function-updated --function-name $FN --region $REGION; drive 5 ;;
  codebug)
    echo "cause: bad code deploy (KeyError)"; aws lambda update-function-configuration --function-name $FN --timeout 10 --memory-size 128 --region $REGION >/dev/null
    aws lambda wait function-updated --function-name $FN --region $REGION; deploy bad_code; drive 5 ;;
  memory)
    echo "cause: config change, memory starves the function (OOM)"; deploy mem_code
    aws lambda update-function-configuration --function-name $FN --timeout 10 --memory-size 128 --region $REGION >/dev/null
    aws lambda wait function-updated --function-name $FN --region $REGION; drive 5 ;;
  throttle)
    echo "cause: reserved concurrency set to 0 (throttles)"; deploy good_code
    aws lambda put-function-concurrency --function-name $FN --reserved-concurrent-executions 0 --region $REGION >/dev/null
    aws cloudwatch put-metric-alarm --alarm-name $TALARM --region $REGION --namespace AWS/Lambda --metric-name Throttles \
      --statistic Sum --period 60 --evaluation-periods 1 --threshold 0 --comparison-operator GreaterThanThreshold \
      --treat-missing-data notBreaching --dimensions Name=FunctionName,Value=$FN >/dev/null; drive 6 ;;
  heal)
    echo "heal: good code, timeout 10, memory 256, remove concurrency cap"; deploy good_code
    aws lambda delete-function-concurrency --function-name $FN --region $REGION 2>/dev/null || true
    aws lambda update-function-configuration --function-name $FN --timeout 10 --memory-size 256 --region $REGION >/dev/null
    aws lambda wait function-updated --function-name $FN --region $REGION
    aws lambda invoke --function-name $FN --payload '{"order_id":"OK"}' --cli-binary-format raw-in-base64-out /tmp/ii_h.json --region $REGION >/dev/null
    echo "   healed -> $(head -c 70 /tmp/ii_h.json)" ;;
  *) echo "unknown: $CMD"; exit 1 ;;
esac
echo "done: $CMD"
