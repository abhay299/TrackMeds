# medtrack API

FastAPI backend. Phase 0: health check + Supabase JWT verification + DB reachability.

## Run locally

```sh
cp .env.example .env         # fill in SUPABASE_URL and DATABASE_URL
uv sync                      # installs Python 3.12 + deps into .venv
uv run uvicorn app.main:app --reload --port 8000
curl localhost:8000/health
```

## Test

```sh
uv run pytest                          # unit tests, no network, no DB
MEDTRACK_INTEGRATION=1 uv run pytest   # also hits the real database via /health/db
uv run ruff check . && uv run ruff format --check .
```

## Container

```sh
docker build -t medtrack-api .
docker run --rm -p 8080:8080 --env-file .env medtrack-api
```

## Deploy to Cloud Run (one-time setup, then `./deploy.sh`)

```sh
brew install --cask google-cloud-sdk
gcloud auth login && gcloud config set project "$GCP_PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com

# The DB password lives in Secret Manager, never in a flag or a file in git.
printf '%s' "$DATABASE_URL" | gcloud secrets create medtrack-database-url --data-file=-
PROJECT_NUMBER=$(gcloud projects describe "$GCP_PROJECT" --format 'value(projectNumber)')
gcloud secrets add-iam-policy-binding medtrack-database-url \
    --member "serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role roles/secretmanager.secretAccessor

# Budget alert at $1 (Console → Billing → Budgets & alerts), then:
export GCP_PROJECT=... SUPABASE_URL=...
./deploy.sh
```

After the first deploy, add an Artifact Registry cleanup policy (keep the 3 newest
images) on the `cloud-run-source-deploy` repository so old builds don't accumulate.

## Current deployment (Phase 0, 2026-09-11)

| | |
|---|---|
| GCP project | `medtrack-api` (billing account in INR; ₹90 gross-spend budget alert, 50/90/100 %) |
| Cloud Run | `medtrack-api`, `asia-south1`, https://medtrack-api-601010886738.asia-south1.run.app |
| Build | `gcloud run deploy --source` → Cloud Build → Artifact Registry `cloud-run-source-deploy` (keeps 3 newest images) |
| Build identity | default compute service account with `roles/cloudbuild.builds.builder` (new projects grant nothing by default) |
| Secrets | `medtrack-database-url` in Secret Manager; runtime SA has `secretAccessor` |
| Supabase | project `avjppsqqyvehsevzbvjh`, Mumbai; ES256 signing keys; sign-ups disabled |

Rotate the DB password: Supabase → Settings → Database → reset, then
`printf '%s' "$NEW_URL" | gcloud secrets versions add medtrack-database-url --data-file=-` and update `.env`.
