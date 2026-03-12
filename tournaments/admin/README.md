# tournaments/admin/

Tournament admin classes split by responsibility.

## Modules

| File | Responsibility |
|------|---------------|
| `tournament_admin.py` | `TournamentAdmin`, `TournamentRegistrationAdmin` |
| `rating_admin.py` | `HostRatingAdmin` |
| `scoring_admin.py` | `GroupAdmin`, `MatchAdmin`, `MatchScoreAdmin`, `RoundScoreAdmin` + `MatchInline`, `MatchScoreInline` |
| `__init__.py` | Imports all submodules to trigger `@admin.register()` side effects |

## Notes

- Unlike views, admin `__init__.py` does NOT need to re-export class names — Django discovers admin by importing the module (which fires the `@admin.register()` decorator).
- `MatchInline` lives in `scoring_admin.py` (not a separate file) because `GroupAdmin` uses `inlines = [MatchInline]` — they must be in the same module.
- `MatchScoreInline` lives alongside `MatchAdmin` for the same reason.
