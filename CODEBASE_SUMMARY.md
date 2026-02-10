# Scrimverse Backend — Codebase Summary

This document summarizes the structure, major components, and important implementation notes for the Scrimverse backend (Django + DRF).

---

## High-level overview

- Type: Django 5.0 REST backend using Django REST Framework (DRF).
- Primary apps: `accounts`, `tournaments`, `payments`.
- Async / background: Celery (Redis broker & result backend).
- Caching: Redis via `django_redis`.
- Auth: Custom `User` model (email as username) + JWT using `djangorestframework-simplejwt`.
- Payment gateway: PhonePe integration wrapped in `payments.services.PhonePeService`.

---

## Repo layout (important files & folders)

- `manage.py` — Django CLI entrypoint.
- `pyproject.toml` — formatting and pytest config.
- `requirements.txt` — runtime dependencies.
- `scrimverse/` — Django project config and core utilities:
  - `scrimverse/settings.py` — full app configuration (DB, S3, Redis, Celery, logging, JWT).
  - `scrimverse/urls.py` — top-level API routes.
  - `scrimverse/celery.py` — Celery app, beat schedule and task discovery.
  - `scrimverse/email_utils.py`, `middleware.py`, `storage_backends.py` — helpers.
- `accounts/` — user, host, player and team management (models, views, serializers, tasks).
- `tournaments/` — tournament domain: models, views, serializers, tasks, signals, pricing, groups and matches logic.
- `payments/` — payment models, PhonePe integration and views.
- `tests/` — pytest-based test suite (unit/integration tests for accounts, payments, tournaments).
- `scripts/` — automation scripts to generate test data and run tournament automation.

---

## Key design & implementation notes

- Custom user model: `accounts.models.User` (email as `USERNAME_FIELD`) with `user_type` (player/host/admin).
- Profiles: `PlayerProfile` and `HostProfile` are one-to-one with `User` and hold domain-specific fields (Aadhar verification for hosts, stats for players).
- Teams & leaderboards: `Team`, `TeamMember`, `TeamStatistics` (in `accounts.models`) store team metadata and leaderboard stats.
- Tournament domain (`tournaments.models`):
  - `Tournament` stores scheduling, plans, rounds (JSON), banners and plan/payment fields.
  - `TournamentRegistration` links `PlayerProfile` to `Tournament` and tracks payment and status.
  - Group / Match / MatchScore / RoundScore implement grouping, match lifecycle and scoring.
  - Round and group metadata are stored as JSONFields for flexible round structures.
- Payments (`payments.models`):
  - `Payment` model tracks merchant/order ids, PhonePe ids, callback data and metadata.
  - `PlanPricing` provides dynamic plan pricing via DB (with sensible defaults in code).
  - `Refund` model for tracking refunds.
- PhonePe integration: `payments.services.PhonePeService` wraps the PhonePe SDK with methods: `initiate_payment`, `create_sdk_order`, `get_order_status`, `initiate_refund`, `get_refund_status`, `validate_callback`.
- Celery: configured in `scrimverse/celery.py`, with a beat schedule for periodic work such as updating tournament statuses, leaderboards, and sending reminders.

---

## API surface (routes)

- Mounted in `scrimverse/urls.py`:
  - `/api/accounts/` -> `accounts.urls` (registration, login, Google OAuth, team management, email verification, password reset)
  - `/api/tournaments/` -> `tournaments.urls` (list, detail, create/update/delete, registration, groups/matches flows)
  - `/api/payments/` -> `payments.urls` (initiate payment, callbacks, refunds)

Refer to each app's `urls.py` for full route lists.

---

## Background jobs & tasks

- Located in each app's `tasks.py` (e.g., `accounts.tasks`, `tournaments.tasks`). Typical responsibilities:
  - Email delivery (verification, welcome, tournament notifications) — tasks queued via Celery.
  - Host/dashboard cache updates and leaderboard recalculation.
  - Periodic tasks scheduled in `scrimverse/celery.py` (beat schedule) to maintain tournament statuses, refresh dashboards, and send reminders.

---

## Caching and performance

- Redis used as a cache backend (`django_redis`) with connection and pooling options configured in `scrimverse/settings.py`.
- Some views use explicit cache keys (e.g., tournaments listing caches `tournaments:list:all`).
- Sessions optionally stored in cache for faster retrieval.

---

## Storage

- Optional S3-based static/media storage controlled by `USE_S3` env var in `scrimverse/settings.py`.
- Custom storage backends are implemented in `scrimverse/storage_backends.py` and `django-storages` + `boto3` are used when enabled.

---

## Authentication & security

- JWT authentication via `djangorestframework-simplejwt` with access/refresh token lifetimes configured in `settings.py`.
- CORS and CSRF trusted origins configured via environment variables.
- Password validators and Django's auth validators are enabled.

---

## Tests

- Pytest + `pytest-django` is used. Configuration is in `pyproject.toml` (DJANGO_SETTINGS_MODULE set to `scrimverse.settings`).
- Tests cover accounts, tournaments, payments and integration scenarios in `tests/`.

---

## How to run (developer steps)

1. Create & activate a virtual environment (Python 3.12+ per project config).
2. Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Set environment variables required by `scrimverse/settings.py` (DB, SECRET_KEY, optional S3 and PhonePe credentials). A minimal set:

```powershell
setx SECRET_KEY "your-secret"
setx DB_NAME "scrimverse_db"
setx DB_USER "postgres"
setx DB_PASSWORD "..."
setx DB_HOST "localhost"
setx DB_PORT "5432"
```

4. Run migrations and create a superuser:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

5. Run the dev server and Celery worker & beat (in separate terminals):

```powershell
python manage.py runserver

# start celery worker
celery -A scrimverse worker --loglevel=info

# start celery beat
celery -A scrimverse beat --loglevel=info
```

6. Run tests:

```powershell
pytest -q
```

---

## Notable files to inspect next

- [scrimverse/settings.py](scrimverse/settings.py) — config surface and operational knobs.
- [scrimverse/celery.py](scrimverse/celery.py) — periodic tasks and Celery config.
- [accounts/models.py](accounts/models.py), [accounts/views.py](accounts/views.py) — auth flows, registration, Google OAuth.
- [tournaments/models.py](tournaments/models.py), [tournaments/views.py](tournaments/views.py) — tournament lifecycle, registration and scoring.
- [payments/services.py](payments/services.py) — PhonePe gateway wrapper and error handling.

---

## Recommendations / quick observations

- Many domain objects store flexible structures in JSONFields (rounds, prize_distribution, selected_teams) — good for flexibility but consider adding migration/validation logic if structure becomes complex.
- Payment metadata currently stores serialized tournament data in `meta_info['tournament_data']` — ensure sensitive fields are not stored and the size stays within PhonePe limits.
- Several background tasks update caches — consistent cache invalidation keys are important (e.g., `tournaments:list:all`).

---

If you want, I can:
- generate a more detailed per-file index (functions/classes/entry points),
- produce a diagram of the main components and data flows, or
- open any of the notable files and extract exact public endpoints and serializer fields.
