#!/usr/bin/env bash
# Deploys the API to Cloud Run. Every flag below is a *cost* decision (docs/decisions.md D2).
#
#   --min-instances 0   scale to zero: idle time is free. 1 would cost ~$10/month.
#   --max-instances 2   hard ceiling on what a bug or a port scan can ever cost.
#   --cpu-throttling    request-based billing: pay only while a request is in flight.
#                       (--no-cpu-throttling = instance-based billing ≈ $9/month here.)
#   --cpu-boost         extra CPU during startup → 1–3 s cold starts instead of 5+.
#
# One-time setup (see README.md): gcloud auth, enable APIs, create the
# DATABASE_URL secret, grant the service account access, set the $1 budget.
set -euo pipefail

: "${GCP_PROJECT:?export GCP_PROJECT=<your gcp project id>}"
: "${SUPABASE_URL:?export SUPABASE_URL=https://<ref>.supabase.co}"

REGION=asia-south1          # Mumbai — Tier 1 pricing, same as Iowa
SERVICE=trackmeds-api

gcloud run deploy "$SERVICE" \
  --project "$GCP_PROJECT" \
  --region "$REGION" \
  --source . \
  --allow-unauthenticated \
  --cpu 1 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 2 \
  --cpu-throttling \
  --cpu-boost \
  --concurrency 80 \
  --timeout 60 \
  --set-env-vars "APP_ENV=prod,SUPABASE_URL=${SUPABASE_URL}" \
  --set-secrets "DATABASE_URL=trackmeds-database-url:latest"

gcloud run services describe "$SERVICE" --project "$GCP_PROJECT" --region "$REGION" \
  --format 'value(status.url)'
