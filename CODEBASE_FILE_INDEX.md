# Scrimverse Backend — Per-File Index (classes & functions)

This file lists the main Python source files and the top-level classes / functions they define. Use it as a quick reference to find entry points and domain objects. It focuses on the primary app files (`accounts`, `tournaments`, `payments`, and `scrimverse`).

---

## Top-level project

- `manage.py`
  - function: `main()` — Django CLI entrypoint

- `pyproject.toml` / `requirements.txt`
  - not Python code; contain tooling / dependency configuration

---

## scrimverse (project)

- `scrimverse/settings.py`
  - Contains project configuration (no top-level classes)

- `scrimverse/celery.py`
  - Celery app: `app` (Celery instance)
  - function/task: `debug_task(self)` — simple test task

- `scrimverse/urls.py`
  - `urlpatterns` (routing) — includes `accounts`, `tournaments`, `payments`

- `scrimverse/email_utils.py` (helper)
  - Various email-sender functions (see file for `send_*` helpers)

- `scrimverse/middleware.py`
  - `NoCacheMiddleware` (middleware class)

- `scrimverse/storage_backends.py`
  - Custom storage backends for `STATICFILES_STORAGE` and `DEFAULT_FILE_STORAGE`

---

## accounts app

- `accounts/models.py`
  - `User` (custom AbstractUser)
  - `PlayerProfile`
  - `HostProfile`
  - `Team`
  - `TeamStatistics`
  - `TeamMember`
  - `TeamJoinRequest`

- `accounts/serializers.py`
  - `UserSerializer`
  - `PlayerProfileSerializer`
  - `HostProfileSerializer`
  - `PlayerRegistrationSerializer`
  - `HostRegistrationSerializer`
  - `LoginSerializer`
  - `TeamMemberSerializer`
  - `TeamSerializer`
  - `TeamJoinRequestSerializer`
  - `TeamStatisticsSerializer`

- `accounts/views.py`
  - `PlayerRegistrationView` (CreateAPIView)
  - `HostRegistrationView` (CreateAPIView)
  - `LoginView` (APIView)
  - `GoogleAuthView` (APIView)
  - `PlayerProfileView` (RetrieveUpdateAPIView)
  - `CurrentPlayerProfileView` (APIView)
  - `HostProfileView` (RetrieveUpdateAPIView)
  - `CurrentHostProfileView` (APIView)
  - `UploadAadharView` (APIView)
  - `CurrentUserView` (APIView)
  - `UserDetailView` (APIView)
  - `PlayerUsernameSearchView` (APIView)
  - `HostSearchView` (APIView)
  - `IsPlayerUser` (permission class)
  - `TeamViewSet` (ModelViewSet)

- `accounts/tasks.py`
  - Celery tasks (shared_task):
    - `update_host_rating_cache(host_id)`
    - `process_team_invitation(team_id, player_id, invitation_type)`
    - Email tasks: `send_welcome_email_task`, `send_verification_email_task`, `send_password_reset_email_task`, `send_aadhar_approval_email_task`, `send_password_changed_email_task`

- `accounts/permissions.py`
  - `IsVerifiedHost` (permission)
  - `IsPlayerUser` (permission)

- `accounts/google_auth.py`
  - `GoogleOAuth` (helper class to verify Google tokens)

---

## tournaments app

- `tournaments/models.py`
  - `Tournament`
    - methods: `__str__`, `get_total_rounds`, `get_round_name`, `get_default_banner_path`, `save`, `can_modify_scrim_structure`
  - `TournamentRegistration`
  - `RoundScore` (with `save` and `calculate_from_matches`)
  - `Group` (with `is_completed`, `get_qualified_teams`)
  - `Match`
  - `MatchScore` (with `save`)
  - `HostRating`

- `tournaments/serializers.py`
  - `TournamentSerializer` (validation + `to_representation`)
  - `TournamentListSerializer`
  - `TournamentRegistrationSerializer` (create, validation helpers)
  - `HostRatingSerializer`
  - `MatchScoreSerializer`
  - `MatchSerializer`

- `tournaments/views.py`
  - Permission classes: `IsHostUser`, `IsPlayerUser`
  - List / detail / CRUD / management views:
    - `TournamentListView`, `TournamentDetailView`, `TournamentCreateView`, `TournamentUpdateView`, `TournamentDeleteView`
    - `HostTournamentsView`, `TournamentRegistrationCreateView`, `PlayerTournamentRegistrationsView`, `PlayerPublicRegistrationsView`
    - Group & match controllers: `StartRoundView`, `SubmitRoundScoresView`, `SelectTeamsView`, `EndRoundView`, `SelectWinnerView`, `TournamentStatsView`, `UpdateTournamentFieldsView`, `EndTournamentView`, `StartTournamentView`, `HostDashboardStatsView`, and others

- `tournaments/groups_views.py`
  - Views handling groups and matches, e.g.: `ConfigureRoundView`, `RoundGroupsListView`, `StartMatchView`, `EndMatchView`, `SubmitMatchScoresView`, `RoundResultsView`, `GetTeamPlayersView`

- `tournaments/tasks.py`
  - Celery tasks (shared_task):
    - `update_tournament_statuses()`
    - `cleanup_unpaid_tournaments_and_registrations()`
    - `send_tournament_reminders_24h()`
    - `send_tournament_reminders_1h()`
    - `update_leaderboard()`
    - `update_platform_statistics()`
    - `update_host_dashboard_stats(host_id)`
    - `refresh_all_host_dashboards()`
    - `process_tournament_registration(registration_id)`
    - `process_round_scores(tournament_id, round_num, scores_data)`
    - `process_match_scores(match_id, scores_data)`
    - `create_tournament_groups(tournament_id, round_number, config)`
    - `process_tournament_banner(tournament_id, image_path)`
    - Many email-sending helper tasks: `send_tournament_registration_email_task`, `send_tournament_created_email_task`, `send_tournament_completed_email_task`, etc.

- `tournaments/services.py`
  - `TournamentGroupService` (helper class): methods like `calculate_groups`, `create_groups_for_round`, `create_matches_for_group`, `calculate_group_standings`, `select_qualifying_teams`, `calculate_round_scores`, `calculate_tournament_winner`

- `tournaments/pricing_views.py`
  - `PlanPricingView` (APIView)

---

## payments app

- `payments/models.py`
  - `PlanPricing` (pricing lookup + `get_price`)
  - `Payment` (tracks merchant ids, PhonePe ids, callback data; `save` adjusts paisa/completed_at)
  - `Refund` (refund tracking; `save` adjusts paisa/completed_at)

- `payments/services.py`
  - `PhonePeService` (singleton-like wrapper around PhonePe SDK)
    - `_initialize_client()`
    - `get_client()`
    - payment methods: `initiate_payment(...)`, `create_sdk_order(...)`, `get_order_status(...)`, `initiate_refund(...)`, `get_refund_status(...)`, `validate_callback(...)`
  - `phonepe_service` (module-level instance)

- `payments/views.py`
  - helper: `convert_to_dict(obj)`
  - API endpoints (DRF view functions): `initiate_payment`, `check_payment_status`, `list_payments`, `initiate_refund`, `phonepe_callback`, and others

- `payments/serializers.py`
  - serializers for initiating payment/refund and for `Payment` and `Refund` objects (see file for exact names)

---

## tests

- `tests/` — pytest-based tests covering:
  - `accounts` tests (auth, registration, teams, Google OAuth, email verification)
  - `tournaments` tests (views, management, scoring, tasks)
  - `payments` tests (gateway integration, views)

---

If you want, I can now:

- expand this to include every Python file in the repository (full exhaustive index), or
- produce a downloadable CSV/JSON of the index, or
- include brief docstrings / first-line summary for each class/function.

Tell me which you prefer and I will update the todo list and proceed.
