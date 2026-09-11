# TrackMeds API

FastAPI backend for TrackMeds. Verifies Supabase-issued JWTs locally (JWKS) and talks to Supabase Postgres through the session pooler.

## Run locally

```sh
cp .env.example .env         # fill in SUPABASE_URL and DATABASE_URL
uv sync                      # installs Python 3.12 + deps into .venv
uv run uvicorn app.main:app --reload --port 8000
curl localhost:8000/health
```

## Test

```sh
uv run pytest                           # unit tests, no network, no DB
TRACKMEDS_INTEGRATION=1 uv run pytest   # also hits the real database via /health/db
uv run ruff check . && uv run ruff format --check .
```

## Container

```sh
docker build -t trackmeds-api .
docker run --rm -p 8080:8080 --env-file .env trackmeds-api
```

## Deploy to Cloud Run

One-time setup for a new GCP project:

```sh
brew install --cask google-cloud-sdk
gcloud auth login
export GCP_PROJECT=<project id>          # currently: medtrack-api
gcloud config set project "$GCP_PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com

# Cloud Build runs as the default compute service account; new projects grant it nothing.
PROJECT_NUMBER=$(gcloud projects describe "$GCP_PROJECT" --format 'value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member "serviceAccount:$SA" --role roles/cloudbuild.builds.builder

# The database URL lives in Secret Manager, never in a flag or a file in git.
printf '%s' "$DATABASE_URL" | gcloud secrets create trackmeds-database-url --data-file=-
gcloud secrets add-iam-policy-binding trackmeds-database-url --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor

# Set a small budget alert on the billing account (Console → Billing → Budgets & alerts).
```

Every deploy after that:

```sh
export GCP_PROJECT=<project id> SUPABASE_URL=https://<ref>.supabase.co
./deploy.sh                  # prints the service URL; flags are pinned for scale-to-zero, request-based billing
scripts/smoke.sh             # signs in as a real user and calls /me and /health/db on the deployed service
```

To rotate the database password: reset it in Supabase, then
`printf '%s' "$NEW_URL" | gcloud secrets versions add trackmeds-database-url --data-file=-` and update `.env`.
