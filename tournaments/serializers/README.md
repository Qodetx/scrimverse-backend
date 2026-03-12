# tournaments/serializers/

Tournament serializers split by model/responsibility.

## Modules

| File | Responsibility |
|------|---------------|
| `tournament.py` | `TournamentSerializer`, `TournamentListSerializer` |
| `registration.py` | `TournamentRegistrationSerializer`, `TournamentRegistrationInitSerializer`, `HostRatingSerializer` |
| `score.py` | `MatchScoreSerializer`, `MatchSerializer` |
| `__init__.py` | Re-exports all — existing `from tournaments.serializers import X` imports unchanged |

## Notes

- `registration.py` imports `TournamentListSerializer` from `tournament.py` (used as nested serializer for the tournament field).
- `TournamentRegistrationInitSerializer` handles the invite-based flow (Step 1 before payment). It does extensive cross-model validation in `validate()`.
- Both `TournamentListSerializer.get_is_registered` and `get_user_registration_status` use lazy imports of `TournamentRegistration` to avoid circular imports.
