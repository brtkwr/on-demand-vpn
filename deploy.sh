#!/usr/bin/env bash
# Deploy the vpn-switch function using the values in .env.
set -euo pipefail
. "$(dirname "$(readlink -f "$0")")/env.sh"
SA=vpn-switch@$GCP_PROJECT.iam.gserviceaccount.com
BUILD_SA=projects/$GCP_PROJECT/serviceAccounts/vpn-switch-build@$GCP_PROJECT.iam.gserviceaccount.com

gcloud functions deploy vpn-switch "${GCLOUD[@]}" --gen2 --runtime python313 --region "$REGION" \
  --source "$ROOT/function" --entry-point vpn --trigger-http --allow-unauthenticated \
  --service-account "$SA" --build-service-account "$BUILD_SA" \
  --set-env-vars "PROJECT=$GCP_PROJECT,ZONE=$ZONE,VM=$VM,VPN_HOST=$VPN_HOST,CF_ZONE=$CF_ZONE" \
  --set-secrets TOKEN=vpn-switch-token:latest,CF_TOKEN=vpn-switch-cf-token:latest \
  --memory 256Mi --max-instances 1 --timeout 150s
