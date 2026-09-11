# Decisions

One paragraph per decision: what we chose, why, and what would change our mind. Newest at the bottom.

## D1 — Native app first, website later, one backend (2026-09-11)
Expo/React Native for Android (iOS later); a React + Vite website only once the app is stable. Two UI codebases are acceptable because **the backend owns every piece of domain logic** (recurrence, dose status, adherence, reminder text) and both clients consume TypeScript types generated from the FastAPI OpenAPI schema. Revisit if the web app turns out to need logic the API doesn't expose — that's a signal the API is too thin, not that the split is wrong.

## D2 — FastAPI on Cloud Run, Mumbai, request-based billing (2026-09-11)
`asia-south1` is Tier‑1 priced; expected cost is $0/month against the free tier (180k vCPU‑s, 360k GiB‑s, 2M requests). The only ways to be charged are configuration: `min-instances ≥ 1` (~$10/mo), instance-based billing / `--no-cpu-throttling` (~$9/mo), unbounded old images in Artifact Registry. `backend/deploy.sh` pins the safe flags; a $1 budget alert catches everything else. Render (free, no card) is the fallback — same Dockerfile.

## D3 — Supabase for Postgres and Auth; JWTs verified locally via JWKS (2026-09-11)
Relational data with real uniqueness constraints → Postgres. Supabase adds Auth for free. The API never calls Supabase to validate a token: it verifies the signature against the project's JWKS endpoint (asymmetric keys must be enabled in the dashboard), so per-request cost is zero and auth keeps working if Supabase Auth blips. All app tables have RLS enabled with no policies, so the anon key shipped in the app cannot read data through PostgREST; only the API (as `postgres`) can. Connect via the Supavisor pooler host — the direct host is IPv6-only.

## D4 — Reminders fire on-device (2026-09-11)
The phone fetches a 14-day `/reminders` window and schedules local notifications (exact alarms). Reminders therefore work offline and never depend on a cold-starting backend. Server push (needed for browser reminders) is deferred; it's feasible at $0 later with Cloud Scheduler hitting a tick endpoint.

## D5 — Schedules are immutable versions; dose instances are computed (2026-09-11)
Editing a schedule ends the old row and inserts a new one, so history stays explainable. Instances are expanded on demand with `dateutil.rrule` and joined to `dose_logs`; nothing generates rows ahead of time, so there is no cron to keep alive on a scale-to-zero host.

## D6 — Product defaults (2026-09-11)
Missed-dose grace 120 min (halved for hourly schedules so it never exceeds half the interval), snooze 30 min, "as needed" medicines deferred to Phase 3, login is email + password only, sign-ups are invite-only.
