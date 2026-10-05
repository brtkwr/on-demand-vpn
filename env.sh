# shellcheck shell=bash disable=SC2034
# Sourced by the scripts: loads .env from the repo root and sets shared helpers.
ROOT=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)
[ -f "$ROOT/.env" ] || { echo "missing $ROOT/.env (copy .env.example)" >&2; exit 1; }
set -a; . "$ROOT/.env"; set +a
WG_CONF=${WG_CONF:-}; WG_CONF=${WG_CONF/#\~/$HOME}
GCLOUD=(--project "$GCP_PROJECT" ${GCP_ACCOUNT:+--account "$GCP_ACCOUNT"})
FUNCTION_URL="https://$REGION-$GCP_PROJECT.cloudfunctions.net/vpn-switch"
