# accounts/serializers/

Account serializers split by model/responsibility.

## Modules

| File | Responsibility |
|------|---------------|
| `user.py` | `UserSerializer`, `PlayerRegistrationSerializer`, `HostRegistrationSerializer`, `LoginSerializer` |
| `profile.py` | `PlayerProfileSerializer`, `HostProfileSerializer` |
| `team.py` | `TeamMemberSerializer`, `TeamSerializer`, `TeamJoinRequestSerializer`, `TeamStatisticsSerializer`, `TeamInviteDetailSerializer` |
| `__init__.py` | Re-exports all — existing `from accounts.serializers import X` imports unchanged |

## Notes

- `profile.py` imports `UserSerializer` from `user.py` (used as nested serializer).
- `team.py` imports `UserSerializer` from `user.py` (used in `TeamMemberSerializer` and `TeamSerializer`).
- `profile.py` imports from `tournaments.models` (HostRating, Tournament, TournamentRegistration) — this is intentional cross-app dependency.
- `tournaments/serializers/` imports `HostProfileSerializer` and `PlayerProfileSerializer` from this package.
