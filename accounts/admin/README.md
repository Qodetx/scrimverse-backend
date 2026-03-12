# accounts/admin/

Account admin classes split by responsibility.

## Modules

| File | Responsibility |
|------|---------------|
| `user_admin.py` | `AadharVerification` (proxy model), `AadharVerificationAdmin`, `UserAdmin` |
| `profile_admin.py` | `PlayerProfileAdmin`, `HostProfileAdmin` |
| `team_admin.py` | `TeamMemberInline`, `TeamAdmin`, `TeamStatisticsAdmin`, `TeamJoinRequestAdmin` |
| `__init__.py` | Imports all submodules to trigger `@admin.register()` side effects |

## Notes

- `AadharVerification` proxy model lives in `user_admin.py` (same file as its admin class).
- Both `AadharVerificationAdmin` and `HostProfileAdmin` send `send_host_approved_email_task.delay()` on approval — each submodule imports this task directly.
- `TeamMemberInline` lives alongside `TeamAdmin` in `team_admin.py` since `TeamAdmin` uses `inlines = [TeamMemberInline]`.
- `__init__.py` imports submodules (not class names) — Django admin discovery is triggered by the import side effect.
