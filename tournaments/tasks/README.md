# tournaments/tasks/

Celery async tasks for the tournaments app, split by responsibility.

## Modules

| File | Responsibility |
|------|---------------|
| `tournament_tasks.py` | Tournament lifecycle: status updates, cleanup, registration processing, group creation, banner processing, platform stats, host dashboard stats |
| `score_tasks.py` | Scoring and leaderboard: `update_leaderboard`, `process_round_scores`, `process_match_scores` |
| `email_tasks.py` | All email notifications: reminder scheduling tasks + thin wrappers around `scrimverse.email_utils` functions |
| `__init__.py` | Re-exports everything — existing `from tournaments.tasks import X` imports work unchanged |

## How to add a new task

1. Put it in the appropriate module (or create a new one if it doesn't fit)
2. Add it to `__init__.py` re-exports
3. Import from `tournaments.tasks` in calling code (never import directly from submodules in external code)
