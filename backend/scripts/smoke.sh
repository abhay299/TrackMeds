#!/usr/bin/env bash
# End-to-end smoke test: sign in to Supabase as a real user, then call the API's
# authenticated DB check. Proves (1) the API accepts genuine Supabase-signed
# tokens and (2) it can reach Postgres from wherever it is deployed.
#
#   backend/scripts/smoke.sh                       # against Cloud Run
#   API_URL=http://localhost:8000 backend/scripts/smoke.sh
#
# Prompts for the publishable key, email and password; nothing is stored or echoed.
set -euo pipefail

SUPABASE_URL="${SUPABASE_URL:-https://avjppsqqyvehsevzbvjh.supabase.co}"
API_URL="${API_URL:-https://trackmeds-api-601010886738.asia-south1.run.app}"

read -r  -p "Supabase publishable key (sb_publishable_...): " KEY
read -r  -p "Login email: " EMAIL
read -rs -p "Password: " PW; echo

LOGIN=$(curl -s -X POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $KEY" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PW\"}")
unset PW

TOKEN=$(printf '%s' "$LOGIN" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))')
if [ -z "$TOKEN" ]; then
  echo "Supabase login failed:"; printf '%s\n' "$LOGIN"; exit 1
fi
echo "signed in; token expires in $(printf '%s' "$LOGIN" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("expires_in"))')s"

echo "GET $API_URL/me"
curl -s -w "\n-> %{http_code}\n" -H "Authorization: Bearer $TOKEN" "$API_URL/me"
echo "GET $API_URL/health/db"
curl -s -w "\n-> %{http_code}\n" -H "Authorization: Bearer $TOKEN" "$API_URL/health/db"
