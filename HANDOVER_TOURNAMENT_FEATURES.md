```markdown
# Handover: Tournament Host & Player Features Implementation (Backend) — Detailed Guide

Last updated: 2026-02-09

Purpose
- This document maps the original requirements (see `task.md`) to the backend implementation, lists code locations, migrations applied, Postman-style request/response examples, verification steps we executed, and precise frontend pickup instructions (where to integrate and how to test). The goal is a clean handoff so frontend engineers can begin immediately.

Summary of implemented features (per `task.md`)
- Simplified invite-based tournament registration flow (captain initiates registration, invites teammates via email, team is created after successful payment; invited players accept/decline via emailed token links).
- Tournament host features:
  - `placement_points` and `prize_distribution` available on the `Tournament` serializer and persisted in DB.
  - Match scheduling fields exposed: `scheduled_date`, `scheduled_time`, `map_name`.
  - Host-only bulk scheduling endpoint to update multiple matches at once.
- Celery task for sending invite emails (works in development using Django console backend).
- Robust payment webhook handling that completes payment, creates Team, issues TeamJoinRequest invites, and queues email tasks.

Where the logic lives (important files)
- Models and migrations
  - `tournaments/models.py` — Tournament, Match, TournamentRegistration, Team, TeamJoinRequest, TeamMember models and JSON fields.
  - Migrations:
    - `tournaments/migrations/0001_initial.py` — initial creation including `prize_distribution` JSON field. (see file)
    - `tournaments/migrations/0002_tournament_discord_id_tournament_rounds_and_more.py` — altered/added tournament fields, ensured `prize_distribution` field settings.
    - `tournaments/migrations/0022_match_map_name_match_scheduled_date_and_more.py` — added `map_name`, `scheduled_date`, `scheduled_time`, `placement_points`, and registration helper fields (`invited_members_status`, `temp_teammate_emails`, `is_team_created`).

- Serializers
  - `tournaments/serializers.py` — `TournamentSerializer` (now includes `placement_points`, `prize_distribution` plus validation), and `MatchSerializer` (now exposes `scheduled_date`, `scheduled_time`, `map_name`).

- Views / Endpoints
  - `tournaments/views.py` — `BulkScheduleUpdateView` (PUT /api/tournaments/{id}/bulk-schedule/), registration views (`register-init`, `register`), and registration helpers.
  - `tournaments/urls.py` — route added for bulk scheduling and registration endpoints.
  - `payments/views.py` — payment webhook handler; on successful payment it routes to registration processing.

- Services & Tasks
  - `tournaments/services_registration.py` — `process_successful_registration()` creates `Team`, `TeamJoinRequest` invites and updates registration state.
  - `tournaments/tasks.py` — `send_team_invite_emails_task` (Celery task that sends invite emails using `scrimverse/email_utils.py`).
  - `scrimverse/email_utils.py` — `EmailService` wrapper and `send_team_invite_email` helper.

Database migrations (files and purpose)
- `tournaments/migrations/0001_initial.py` — initial schema: created `Tournament` model and included `prize_distribution` JSONField (default=dict).
- `tournaments/migrations/0002_tournament_discord_id_tournament_rounds_and_more.py` — added tournament metadata fields (discord_id, rounds, tournament_date/time, and updated `prize_distribution` attributes).
- `tournaments/migrations/0022_match_map_name_match_scheduled_date_and_more.py` — added:
  - `match.map_name` (CharField)
  - `match.scheduled_date` (DateField)
  - `match.scheduled_time` (TimeField)
  - `tournament.placement_points` (JSONField)
  - `tournamentregistration.invited_members_status` (JSONField)
  - `tournamentregistration.temp_teammate_emails` (JSONField)
  - `tournamentregistration.is_team_created` (BooleanField)

Note: run `python manage.py showmigrations tournaments` and `python manage.py migrate` to confirm migrations are applied in each environment.

API Reference & Postman-style examples
Authentication
- All protected endpoints require JWT bearer token in the `Authorization` header.

1) Register-init (create pending registration)
- URL: POST `/api/tournaments/{tournament_id}/register-init/`
- Auth: required (logged-in user who will act as captain)
- Request body example:
```
{
  "team_name": "Alpha Squad",
  "captain_username": "player2",
  "temp_teammate_emails": ["teammate2@example.com","teammate3@example.com"]
}
```
- Expected response (201 Created):
```
{
  "id": 17,
  "tournament": 5,
  "team_name": "Alpha Squad",
  "status": "pending",
  "temp_teammate_emails": ["teammate2@example.com","teammate3@example.com"],
  "invited_members_status": {
    "teammate2@example.com": {"status":"pending","username":null},
    "teammate3@example.com": {"status":"pending","username":null}
  }
}
```

2) Start payment (initiate payment for entry fee)
- URL: POST `/api/payments/start/` (or tournament-specific payment endpoint depending on integration)
- Request body example (simplified):
```
{
  "registration_id": 17,
  "amount": "500.00",
  "currency": "INR",
  "metadata": {"registration_id":17,"tournament_id":5}
}
```
- Expected response (200):
```
{
  "merchant_order_id": "mord-12345-20260209",
  "payment_url": "https://phonepe.example.com/pay/..",
  "payment_id": "pay-abcdef"
}
```

3) Payment webhook (server receives callback)
- URL: POST `/api/payments/webhook/`
- This is called by the payment provider; for local dev you can simulate by POSTing to this endpoint with `merchant_order_id` matching DB `Payment` record.
- Sample request body (simplified):
```
{
  "merchant_order_id": "mord-12345-20260209",
  "status": "SUCCESS",
  "payment_id": "pay-abcdef",
  "amount": "500.00"
}
```
- Server behavior on success:
  - Marks `Payment` record completed.
  - If metadata indicates a tournament registration: calls `process_successful_registration()` which:
    - Creates `Team` and `TeamJoinRequest` invite records
    - Updates `TournamentRegistration.invited_members_status` with invite tokens and `status: pending`
    - Sets `tournamentregistration.is_team_created = True`
    - Queues the `send_team_invite_emails_task` Celery task

- Expected webhook handler response: HTTP 200 OK with acknowledgement body (provider-specific); backend logs show processing details. If any internal error occurred previously this endpoint may have raised an UnboundLocalError; that legacy bug has been fixed.

4) Accept invite
- URL: POST `/api/invites/accept/`
- Request body:
```
{ "invite_token": "invite-abc-xyz" }
```
- Behavior:
  - Validates the token, ensures user is logged in (or prompts to sign up / login), attaches player to the Team automatically, updates `TeamJoinRequest` status and `TournamentRegistration.invited_members_status` entry to `accepted` with username.
- Expected response (200): success message + team membership payload.

5) Bulk schedule (host-only)
- URL: PUT `/api/tournaments/{tournament_id}/bulk-schedule/`
- Auth: required (must be tournament host)
- Body formats accepted (server accepts multiple shapes):
  - Top-level array of schedule objects:
```
[
  { "match_id": 1, "scheduled_date":"2026-02-10", "scheduled_time":"18:00", "map_name":"Map A" },
  { "match_id": 2, "scheduled_date":"2026-02-10", "scheduled_time":"18:30", "map_name":"Map B" }
]
```
  - Or object with `schedules` key: `{ "schedules": [ ... ] }`
- Server response example (200):
```
{ "updated_count": 2, "updated_ids": [1,2], "errors": [] }
```

How we tested (what we ran & verification)
- Register / invite flow:
  - Performed `register-init` to create a pending `TournamentRegistration` with `temp_teammate_emails` and `invited_members_status` set to pending for each email.
  - Started payment and created a `Payment` DB record with `merchant_order_id`.
  - Simulated payment webhook to `/api/payments/webhook/` with that `merchant_order_id`.
  - Verified server created `Team` and `TeamJoinRequest` invite records in DB and updated `TournamentRegistration.is_team_created = True`.
  - Started a Celery worker (solo pool on Windows) and confirmed `send_team_invite_emails_task` executed and logs printed the email contents (console backend) and success messages.

- Bulk scheduling:
  - Created `Group` and three `Match` rows via Django shell.
  - Called PUT `/api/tournaments/{id}/bulk-schedule/` with an array payload; initially the view required a list and returned an error for alternative payload shapes — view was patched to accept array OR `{ schedules: [...] }` OR raw body parsed fallback.
  - After patching, repeat PUT returned `{ updated_count: 3 }` and DB `Match` rows showed `scheduled_date`, `scheduled_time`, `map_name` set.

- Webhook robustness:
  - During tests webhook raised an `UnboundLocalError` in legacy branch; patched to initialize legacy variables prior to conditional use. Re-tested and confirmed no crashes.

Dev commands / environment notes
- Run migrations and dev server:
```bash
python manage.py showmigrations tournaments
python manage.py migrate
python manage.py runserver
```
- Start Celery worker on Windows (use `solo` or `threads` pool):
```bash
celery -A scrimverse worker -l info -P solo
# or
celery -A scrimverse worker -l info -P threads --concurrency=4
```
- Console email backend: in development `EMAIL_BACKEND` is set to Django console backend; invite email contains the accept link and token printed to the server console.

Frontend integration details (where and how to pick up work — no code included)
This section maps each requirement in `task.md` to frontend responsibilities, the pages/components to update, the API calls to make, and the test theory.

1) Invite-based registration flow
- Pages & places to add:
  - Registration UI: `src/pages/CreateTournament.js` and `src/pages/PlayerRegister.js` (or the existing tournament registration page in `src/pages/PlayerRegister.js` / `CreateScrim.js` depending on your routing).
  - Add Team Registration component that allows a logged-in user to enter a `team_name` and up to N teammate emails.
- API calls:
  - POST `/api/tournaments/{id}/register-init/` to create pending registration.
  - POST payment start endpoint to get `merchant_order_id`.
  - For development, simulate webhook by POSTing to `/api/payments/webhook/` or use test payment flow configured by backend.
- UX expectations & test theory:
  - After `register-init`, the UI should show registration status as `pending` with the list of invited emails and their statuses.
  - After successful payment (webhook processed), the frontend should either poll registration/team endpoint or receive push (if implemented later) to discover team created and invites sent.
  - Use the server console to copy invite link (include token) during dev and test `AcceptInvite` flow by opening the link which should hit frontend route `invite/accept?token=...`.

2) Accept / Decline invite
- Pages & places to add:
  - `src/pages/AcceptInvite.js` (route `/invite/accept`) to read `?token=` query param and call POST `/api/invites/accept/`.
  - `src/pages/DeclineInvite.js` or reuse Accept page with decline action.
- API calls:
  - POST `/api/invites/accept/` { invite_token }
  - POST `/api/invites/decline/` { invite_token }
- UX & test theory:
  - If user is not logged in, prompt to login/signup (Google auth flow allowed). After login, automatically continue token acceptance and add user to team.
  - On success show a confirmation and redirect to player dashboard.

3) Match visibility and player dashboard
- Pages & places to add:
  - `src/pages/PlayerDashboard.js` and tournament details pages in `src/pages/TournamentDetail.js` or `ScrimDetail.js`.
- API calls:
  - GET `/api/tournaments/{id}/matches/` (or included in tournament detail response) to fetch match list with `match_number`, `group`, `map_name`, `scheduled_date`, `scheduled_time`.
- UX & test theory:
  - Display a time section listing matches with match number, group assignment, date, time, and map.
  - For live updates: implement polling (GET every 15–60s) until backend pushes real-time updates.

4) Host bulk scheduling
- Pages & places to add:
  - `src/pages/ManageTournament.js` — add `BulkScheduleForm` or table where host can set date/time/map per match.
- API calls:
  - PUT `/api/tournaments/{tournament_id}/bulk-schedule/` with array of `{ match_id, scheduled_date, scheduled_time, map_name }`.
- UX & test theory:
  - After saving, show feedback with `updated_count` and any `errors` returned from server.
  - Immediately refresh matches list after success. Until push notifications are implemented, use polling or client refresh to reflect host changes to players.

5) Prize pool and points configuration (host side)
- Pages & places to add:
  - `src/pages/CreateTournament.js` and `src/pages/ManageTournament.js` — provide inputs for total prize pool, prize distribution (structured input), and `placement_points` mapping.
- API calls:
  - POST / PUT tournament create/update endpoints that accept `prize_distribution` (JSON) and `placement_points` (JSON).
- UX & test theory:
  - Validation on frontend to ensure prize totals make sense (sum matches total prize pool if required).
  - On saving, verify via GET tournament detail that fields persisted.

Notes on real-time sync (recommendation)
- Short-term: implement client polling for match lists: call GET `/api/tournaments/{id}/matches/` every 30s or when host performs bulk schedule, trigger client-side refresh.
- Longer-term: add Django Channels + WebSocket to push `match_scheduled` events to clients; this requires backend Channels implementation and a small frontend WebSocket client to update pages in real-time.

Additional handover items & recommended next tasks
- Create a Postman collection / OpenAPI spec with examples above for all endpoints (I can produce this on request).
- Add automated tests (Django) for:
  - Webhook → `process_successful_registration()` → team creation and invites
  - `BulkScheduleUpdateView` payload parsing and permission checks
  - Invite accept/decline flows
- Confirm applied migrations on staging and production and run `python manage.py migrate` before deployment.

Appendix — quick references
- Key file list (quick links):
  - `tournaments/models.py`
  - `tournaments/serializers.py`
  - `tournaments/views.py`
  - `tournaments/urls.py`
  - `tournaments/tasks.py`
  - `tournaments/services_registration.py`
  - `payments/views.py`
  - `scrimverse/email_utils.py`
  - `scrimverse/celery.py`

If you want, I can now:
- Produce a Postman collection with example requests/responses and environment variables.
- Create a minimal OpenAPI snippet for the new endpoints.
- Add a short frontend acceptance test plan (step-by-step manual checklist) that QA can follow.

Pick one of the items above and I'll add it to the repo next.

```
