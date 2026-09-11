# TrackMeds

TrackMeds is a medication reminder app for a small group of people. Medicines can be scheduled daily, on specific weekdays, every few days, or every few hours. The app reminds you on your phone and keeps a log of what was taken, skipped, or missed.

- `backend/` — FastAPI (Python 3.12) API that owns schedules, dose expansion and history. Runs on Google Cloud Run.
- `apps/mobile/` — Expo (React Native) app for Android; iOS later.
- Supabase provides Postgres and authentication.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 itself)
- Node.js 22+ and [pnpm](https://pnpm.io/)
- A Supabase project with email sign-in enabled, public sign-ups disabled, and asymmetric (ES256) JWT signing keys
- An Android phone with USB debugging enabled

## Backend

```sh
cd backend
cp .env.example .env        # set SUPABASE_URL and DATABASE_URL (use the session-pooler host)
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
```

Deployment to Cloud Run is described in [`backend/README.md`](backend/README.md).

## Mobile app

```sh
cd apps/mobile
cp .env.example .env        # Supabase URL, publishable key, API URL
pnpm install
pnpm android                # installs Expo Go if needed and opens the app on the connected phone
```

Sign in with a user created in the Supabase dashboard (Authentication → Users → Add user).

## Documentation

- [`docs/plan.md`](docs/plan.md) — architecture and delivery phases
- [`docs/decisions.md`](docs/decisions.md) — why each choice was made
