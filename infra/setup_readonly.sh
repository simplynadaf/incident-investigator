#!/usr/bin/env bash
# Create a READ-ONLY identity for the investigator and prove it cannot remediate.
# The investigator runs under this profile on camera. A write attempt returns AccessDenied.
set -euo pipefail
U=demo-ii-readonly
PROFILE=ii-readonly
ACCT=$(aws sts get-caller-identity --query Account --output text)

if ! aws iam get-user --user-name $U >/dev/null 2>&1; then
  aws iam create-user --user-name $U >/dev/null
fi
# only read: ReadOnlyAccess covers Describe/Get/List/FilterLogEvents/lookup-events across services
aws iam attach-user-policy --user-name $U --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess

# fresh access key for the profile (rotate: delete old keys first)
for k in $(aws iam list-access-keys --user-name $U --query 'AccessKeyMetadata[].AccessKeyId' --output text); do
  aws iam delete-access-key --user-name $U --access-key-id "$k" 2>/dev/null || true
done
KEY_JSON=$(aws iam create-access-key --user-name $U --output json)
AK=$(echo "$KEY_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['AccessKey']['AccessKeyId'])")
SK=$(echo "$KEY_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['AccessKey']['SecretAccessKey'])")
aws configure set aws_access_key_id "$AK" --profile $PROFILE
aws configure set aws_secret_access_key "$SK" --profile $PROFILE
aws configure set region us-east-1 --profile $PROFILE
echo "read-only profile '$PROFILE' ready (user $U, ReadOnlyAccess). key id ${AK:0:8}..."
sleep 12  # let IAM propagate
echo "== proof it can READ:"; aws cloudwatch describe-alarms --alarm-names demo-ii-orders-errors --profile $PROFILE --query 'MetricAlarms[].StateValue' --output text 2>&1 | head -1
echo "== proof it CANNOT write (expect AccessDenied):"
aws lambda update-function-configuration --function-name demo-ii-orders-api --timeout 10 --profile $PROFILE 2>&1 | grep -o "AccessDenied[A-Za-z]*\|not authorized to perform[^.]*" | head -1 || echo "  (unexpected: write was allowed)"
