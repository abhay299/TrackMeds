# Medication Reminder App — End-to-End Plan

Working name: **medtrack** (rename any time; it only affects folder/app names).

## Context

Abhay and 3–4 other people take medicines on mixed cadences — daily, specific weekdays, alternate days, every N hours, sometimes a fixed-length course. Existing apps (MyTherapy, Medisafe) do this but this is a personal build: **Android app first, website later, iOS maybe**, backend in **Python/FastAPI**, everything on **free tiers**, traffic ≈ zero. It is also a learning project: decisions are explained, each phase is built only when the previous one is proven, no infrastructure is added ahead of the problem it solves.

The one thing a medication app cannot get wrong is *the reminder firing*. Every architectural choice below is downstream of that.

## Decisions (locked in discussion)

| Area | Choice | Why |
|---|---|---|
| Mobile app | **Expo (React Native)** + Expo Router + **React Native Paper** (MD3) + TanStack Query + react-hook-form/zod + supabase-js | Native feel, first-class iOS later, EAS Update for OTA fixes (no APK reinstalls for 4 users). Paper gives Android-native components + pickers with least UI work. |
| Web app | **Later**: React + Vite, same API | Built once the app is stable. Shares generated API types, not UI code. |
| Backend | **FastAPI**, Python 3.12, `uv`, SQLAlchemy 2 (async, asyncpg), Alembic, PyJWT, python-dateutil | Your stack; rrule does the recurrence math; Alembic owns the schema. |
| API hosting | **Cloud Run, `asia-south1` (Mumbai)**, request-based billing, `min-instances 0`, `max-instances 2`, default CPU throttling, $1 budget alert | Tier‑1 region (same price as Iowa), ~1–3 s cold start, expected **$0/mo** (≈ pennies of egress). The three ways to get billed are all config, and the deploy script pins them. |
| Data + Auth | **Supabase (Mumbai)**: Postgres via Supavisor pooler; Supabase Auth, email+password, **invite-only** | Relational data with uniqueness constraints; Auth for free; JWT verified in FastAPI via JWKS. Free plan: 500 MB, pauses after 7 idle days (impossible with daily use). |
| Reminders | **On-device local notifications** scheduled from a 14‑day dose window; `expo-notifications` first, `react-native-notify-kit` (maintained Notifee fork) as fallback after a real-device reliability gate | Fires offline, survives any backend cold start/outage, needs no always-on server. Server push for the web is an optional later phase. |
| Distribution | EAS Build preview APK (15 free Android builds/mo) or local Gradle build → GitHub Release; **EAS Update** for JS-only changes (1,000 MAU free) | No Play Store needed for 4 people. |
| Cost | **$0/year** expected. Only mandatory non-money cost: a card on the GCP billing account. | |

Two guardrails that make "web later" cheap:
1. **The backend owns all domain logic** — recurrence expansion, dose status, adherence math, even the reminder text. Clients render and, on the phone, schedule alarms.
2. **One contract** — TypeScript types generated from FastAPI's OpenAPI schema into `packages/api-types`, consumed by mobile now and web later.

## Architecture

```
┌───────────────────────────────┐        HTTPS + Bearer JWT        ┌──────────────────────────┐
│ Expo app (Android; iOS later) │ ───────────────────────────────▶ │ FastAPI on Cloud Run     │
│  • Today / Meds / History     │                                  │  asia-south1, scale→0    │
│  • schedules local alarms     │ ◀─── GET /reminders (14d) ────── │  • recurrence engine     │
│    from the reminder window   │                                  │  • dose status/adherence │
└──────┬────────────────────────┘                                  └──────────┬───────────────┘
       │ supabase-js (login, refresh)                                          │ asyncpg via pooler
       ▼                                                                       ▼
┌──────────────────┐                                                ┌──────────────────────────┐
│ Supabase Auth    │  same project, JWKS verifies tokens ─────────▶ │ Supabase Postgres        │
│ (invite-only)    │                                                │ RLS on, no policies      │
└──────────────────┘                                                └──────────────────────────┘
       ▲
       │ later: React + Vite web app → same API (same generated types)
```

Request path: app → `Authorization: Bearer <supabase access token>` → FastAPI `current_user` dependency verifies signature against `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` (PyJWKClient, cached; `audience="authenticated"`; requires **asymmetric signing keys** enabled in the Supabase dashboard) → `sub` is the user id → every query filters by it.

Defense in depth: **RLS enabled on every app table with no policies**, so the anon/authenticated keys that live in the app can log in but cannot read tables through PostgREST. FastAPI connects as `postgres` (bypasses RLS). Connect through the pooler host (`*.pooler.supabase.com`, session mode, port 5432) — the direct host is IPv6-only.

## Domain model

### Schedules are immutable versions

Editing a schedule in place would rewrite history ("was Tuesday's 8 AM dose missed?" depends on what the schedule *was*). So a schedule row is never edited: **edit = end the old row (`ends_at = now`) + insert a new row with `replaces_schedule_id`**. Past instances stay computable; the app shows the medication's current (open) schedule.

### Tables (Alembic-managed, `public` schema)

```
profiles        id (= auth.users.id) · display_name · tz (IANA, e.g. Asia/Kolkata) · missed_grace_minutes (default 120) · created_at
medications     id · user_id · name · strength ("500 mg") · form (tablet|capsule|liquid|injection|other) · notes · archived_at · created_at
schedules       id · user_id · medication_id
                kind: daily | weekly | every_n_days | every_n_hours | as_needed
                times_of_day  time[]     -- local wall-clock; daily/weekly/every_n_days
                days_of_week  int[]      -- weekly (0=Mon..6=Sun)
                interval      int        -- every_n_days / every_n_hours
                starts_at     timestamptz -- anchor: local midnight of start date, or first dose time for hourly
                ends_at       timestamptz null -- exclusive; set by course end, "end", or replace
                total_doses   int null   -- alternative course length (rrule count)
                tz            text       -- captured from the device at creation
                dose_amount numeric · dose_unit text · instructions text null
                replaces_schedule_id uuid null · created_at
dose_logs       id · user_id · medication_id · schedule_id
                scheduled_at  timestamptz null   -- the instance key (null for as-needed logs)
                status: taken | skipped · taken_at timestamptz · note · source (app|notification|web) · created_at
                UNIQUE (schedule_id, scheduled_at)
```

### Dose instances are computed, never stored

Materialising future doses needs a generator job (a cron on a scale-to-zero host) and re-generation on every edit. Instead the backend expands schedules on demand for any window and left-joins `dose_logs`. Status is derived:

```
log exists            → log.status (taken | skipped)
now < scheduled_at    → upcoming
now ≤ scheduled_at + grace → due          (grace = min(profile grace, interval/2 for hourly))
else                  → missed
```

Adherence (Phase 3) = taken / (taken + skipped + missed) over a range, per medication — same expansion, older window.

## Recurrence engine (`backend/app/services/recurrence.py`)

Pure functions, the most-tested code in the repo. `expand(schedule, window_start_utc, window_end_utc) -> list[datetime]`.

| kind | dateutil rrule |
|---|---|
| daily | one `rrule(DAILY, byhour=h, byminute=m)` **per time_of_day**, merged with `rruleset` |
| weekly | per time: `rrule(WEEKLY, byweekday=[…], byhour=h, byminute=m)` |
| every_n_days | per time: `rrule(DAILY, interval=n, …)` — `dtstart` (local midnight of start date) fixes the day parity |
| every_n_hours | `rrule(HOURLY, interval=n, dtstart=starts_at)`, iterated in UTC so intervals stay exact |
| as_needed | no instances |

Rules that matter:
- **One rrule per time of day.** Passing `byhour=[8,20], byminute=[0,30]` yields the cross product (08:30, 20:00 …) — a classic bug.
- Day-based kinds iterate in the schedule's tz as wall-clock (`zoneinfo`), then convert to UTC — "08:00" stays 08:00 across DST; India has no DST but the tests include `America/New_York` to prove it.
- `ends_at` clips (exclusive); `total_doses` maps to rrule `count`.
- `/reminders` groups instances by minute into one notification each — this is also Android's Doze rule (allow-while-idle alarms fire at most once per 9 min per app).

## API v1 (`backend/app/api/v1/`)

```
GET    /health
GET    /me                       profile (auto-created on first call; tz from X-Timezone header)
PATCH  /me                       tz, grace
GET    /medications              active (+ ?archived=true)
POST   /medications              {name, strength, form, notes, schedule: {...}}   creates med + first schedule
PATCH  /medications/{id}         name/strength/notes only
DELETE /medications/{id}         archive; ends open schedules
POST   /medications/{id}/schedules          add another schedule (e.g. different dose at night)
PUT    /schedules/{id}           replace: ends old, creates new (returns new)
DELETE /schedules/{id}           end now
GET    /doses?from=&to=          expanded instances + status (client passes UTC bounds of its local day)
GET    /reminders?from=&to=      minute-grouped: [{at, title, body, instances:[{schedule_id, scheduled_at}]}]
POST   /doses/log                {schedule_id, scheduled_at|null, status, taken_at?, note?}  upsert on the unique key
DELETE /doses/log/{id}           undo
GET    /adherence?from=&to=      (Phase 3)
```

All endpoints are per-user via `current_user`; ids that don't belong to the caller 404.

## Reminder engine (phone)

```
trigger: app foregrounded · schedule changed · dose logged · notification acted on · (daily 12-day safety)
  groups   = GET /reminders?from=now&to=now+14d
  cancelAllScheduledNotifications()                      -- simplest idempotent strategy
  for g in groups[:200]:                                  -- Android caps ~500 alarms/app
      schedule(at=g.at, title=g.title, body=g.body, data=g.instances, category="DOSE", exact=true)
  schedule(at=now+12d, "Open medtrack to keep reminders going")
```

- Actions on the notification: **Take · Snooze 10 min · Skip** → `POST /doses/log` per instance (snooze = one-off local notification with the same payload). Cold-launch responses handled via `getLastNotificationResponse`.
- Permissions: `POST_NOTIFICATIONS` (Android 13+ runtime) and **`USE_EXACT_ALARM`** — legitimate for an alarm-class app, auto-granted, and we sideload so Play policy doesn't apply; avoids the "grant exact alarms in Settings" dance.
- One-time **reliability checklist** screen: disable battery optimisation, OEM autostart (Xiaomi/Oppo/Vivo/Samsung) — the same guidance MyTherapy/Medisafe give.
- Today screen renders from a persisted TanStack Query cache, so a Cloud Run cold start is invisible.
- **Gate before building on it (Phase 2 spike):** schedule test notifications, then screen off + `adb shell dumpsys deviceidle force-idle` + app force-stopped + reboot. All fire within a minute → keep `expo-notifications`. Otherwise → `react-native-notify-kit` (`SET_EXACT_AND_ALLOW_WHILE_IDLE`, exposes the exact-alarm setting check that expo-notifications lacks).

## Repo layout (monorepo, `~/dev/medtrack`)

```
backend/
  app/main.py · core/{config,db,security}.py · models/ · schemas/ · api/v1/{me,medications,schedules,doses}.py
  app/services/{recurrence.py,doses.py,reminders.py}
  alembic/ · tests/ · Dockerfile · pyproject.toml (uv) · deploy.sh (pinned Cloud Run flags)
apps/mobile/          Expo: app/(tabs)/{today,meds,history,settings}.tsx · src/{api,auth,notifications,features}
apps/web/             later
packages/api-types/   generated from backend OpenAPI (openapi-typescript)
.github/workflows/    backend-ci.yml (ruff + pytest) · deploy-backend.yml (Phase 3)
docs/                 decisions.md (ADR-style, one paragraph per decision) · android-reliability.md
```

## Phases — one at a time, each with an exit criterion

### Phase 0 — Walking skeleton (prove every integration once)
1. Supabase project (Mumbai): enable asymmetric JWT signing keys, disable public sign-ups, invite one user, note pooler URL + JWKS URL.
2. Backend: `uv init`; FastAPI with `/health` and JWT-protected `/me`; pydantic-settings; async engine doing `SELECT 1`; Dockerfile (`python:3.12-slim`, uv, non-root, port 8080). Runs locally against Supabase.
3. GCP: project + billing + **$1 budget alert**; `gcloud run deploy --source .` to `asia-south1` with `--min-instances 0 --max-instances 2 --cpu 1 --memory 512Mi --cpu-boost` (leave CPU throttling on = request-based billing); Artifact Registry cleanup policy "keep last 3". `curl /health`.
4. Mobile: `create-expo-app` (TS), Expo Router tabs, RN Paper, supabase-js (AsyncStorage adapter), login screen, `/me` shown on Today. Dev build on your phone via USB (`npx expo run:android`; EAS dev build as alternative).
- **Exit:** phone → login → authenticated `/me` from Cloud Run. Billing report after a week reads $0.

### Phase 1 — Domain core (the mentoring-heavy phase)
- Alembic migrations for the four tables + RLS-on/no-policy hardening.
- `recurrence.py` with parametrised tests: daily ×2, weekly MWF, every-2-days across a month boundary and across a DST change, every-6-hours with `total_doses=20`, `ends_at` clipping, window edges, cross-product regression test.
- Endpoints: medications, schedules (create/replace/end), `/doses`, `/doses/log`, undo.
- App: Meds list · Add/Edit medication with schedule form (kind picker → conditional fields, Paper time pickers, tz from device) · Today (grouped by time, Take/Skip, pull-to-refresh, persisted cache).
- **Exit:** create "Metformin 500 mg daily 08:00 & 20:00" and "Vitamin D3 every 2 days 09:00" on the phone; Today and tomorrow show the right instances; logging works; refreshing preserves state.

### Phase 2 — Reminders
- Run the reliability spike above; pick the notification library.
- Sync-and-schedule, minute grouping, actions, snooze, cold-launch handling, safety notification, permissions + reliability checklist screen, `missed` state on Today.
- **Exit:** a week of your real meds reminded on your phone with the app killed and screen off — zero misses.

### Phase 3 — Daily-use hardening + hand-off to the other users
- History/adherence screen; edit/end/pause schedule UX (versioning); as-needed meds with quick-log.
- Offline queue for logs (replay on reconnect; unique-constraint conflict = already logged = success).
- CI: ruff + pytest on PR; deploy on `main` (Alembic upgrade runs in the workflow, **not** at container start).
- EAS Update channel; preview APK on a GitHub Release; invite the other users.
- Backup: weekly `pg_dump` GitHub Action (Supabase free has no backups).

### Phase 4 — Later, only when wanted
- **Web app** (React + Vite + generated types) on Cloudflare Pages/Vercel free.
- Inventory & refill reminders (decrement on `taken`).
- **Server push** for web/backup: Cloud Scheduler (3 free jobs) hits `/internal/tick` every minute → FCM/Web Push; still $0 on Cloud Run.
- iOS: Apple Developer ($99/yr) → EAS iOS build → TestFlight. Caregiver read-only sharing. PDF report.

## Risks & gotchas (known up front)

- **OEM battery killers** are the #1 cause of missed reminders on Android — hence the checklist screen and the USE_EXACT_ALARM choice.
- `expo-notifications` background flakiness is documented; the Phase 2 gate exists so we never build on a library that fails on *your* phone.
- Notifee is archived (Apr 2026); the fork is community-maintained — a reason to prefer expo-notifications if it passes.
- Cloud Run billing footguns: `min-instances ≥ 1` (~$10/mo), instance-based billing (~$9/mo), forgotten images. All pinned in `deploy.sh`; budget alert catches the rest.
- Supabase free project pauses after 7 idle days — daily use prevents it; one-click restore if not.
- Alarm cap (~500/app) and Doze 9-minute throttle — handled by the 200-notification cap and minute grouping.
- Timezones: schedules carry their tz; hourly kinds iterate in UTC; tests cover DST even though IST has none.
- Cold starts: 1–3 s on Cloud Run, hidden by the persisted cache; the reminder path never touches the server.

## Verification

- **Backend:** `uv run pytest` — recurrence unit tests + API tests against Postgres in Docker (auth dependency overridden). `ruff check`.
- **Deploy:** `curl https://<service>.a.run.app/health`; `/me` with a real token from the app.
- **Phone:** dev build on your physical device; Phase 2 device checklist (screen off, forced Doze, force-stop, reboot); actions log doses visible on Today.
- **Cost:** GCP billing report = $0 after week 1 and month 1; Supabase usage well under 500 MB.

## Open for discussion

1. App name (only affects folder/app id).
2. Missed-dose grace default (2 h?) and snooze length (10 min?).
3. Should "as needed" meds be in Phase 1 or Phase 3?
4. Login: email+password only, or also Google sign-in?
