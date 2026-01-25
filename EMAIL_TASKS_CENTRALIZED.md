# ✅ Email Tasks Centralized in accounts/tasks.py

## What Changed

All email-related Celery tasks have been moved to a single location for better organization and maintainability.

## File Structure

```
scrimverse-backend/
├── accounts/
│   ├── tasks.py                    ✅ ALL EMAIL TASKS HERE
│   └── views.py                    ✅ Imports from accounts.tasks
│
├── scrimverse/
│   ├── email_utils.py              ✅ Email service functions (unchanged)
│   └── email_tasks.py              ⚠️  DEPRECATED - Use accounts/tasks.py instead
│
└── templates/emails/               ✅ Email templates (unchanged)
```

## Email Tasks Location

**New Location**: `accounts/tasks.py`

All 11 email tasks are now in one place:

### Account & Security (3 tasks)
1. `send_welcome_email_task` - Welcome email after registration
2. `send_password_reset_email_task` - Password reset request
3. `send_password_changed_email_task` - Password change confirmation

### Tournament - Player Side (3 tasks)
4. `send_tournament_registration_email_task` - Registration confirmation
5. `send_tournament_results_email_task` - Results published
6. `send_premium_tournament_promo_email_task` - Premium tournament promo

### Tournament - Host Side (5 tasks)
7. `send_host_approved_email_task` - Host account approved
8. `send_tournament_created_email_task` - Tournament created
9. `send_tournament_reminder_email_task` - Tournament reminder
10. `send_registration_limit_reached_email_task` - Registration full
11. `send_tournament_completed_email_task` - Tournament completed

## How to Use

### Import from accounts.tasks

```python
# In any view file
from accounts.tasks import send_welcome_email_task

# Use the task
send_welcome_email_task.delay(
    user_email=user.email,
    user_name=user.username,
    dashboard_url=dashboard_url,
    user_type='player'
)
```

### Example: Player Registration

```python
# accounts/views.py
from accounts.tasks import send_welcome_email_task

class PlayerRegistrationView(generics.CreateAPIView):
    def create(self, request, *args, **kwargs):
        # ... create user ...

        # Send welcome email
        send_welcome_email_task.delay(
            user_email=user.email,
            user_name=user.username,
            dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard",
            user_type='player'
        )

        return Response(...)
```

### Example: Tournament Registration

```python
# tournaments/views.py
from accounts.tasks import send_tournament_registration_email_task

class TournamentRegistrationCreateView(generics.CreateAPIView):
    def perform_create(self, serializer):
        registration = serializer.save()

        # Send confirmation email
        send_tournament_registration_email_task.delay(
            user_email=registration.user.email,
            user_name=registration.user.username,
            tournament_name=registration.tournament.name,
            game_name=registration.tournament.game.name,
            start_date=registration.tournament.start_date.strftime("%B %d, %Y at %I:%M %p"),
            registration_id=str(registration.id),
            tournament_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/tournaments/{registration.tournament.id}",
            team_name=registration.team_name
        )
```

## Benefits of Centralization

### ✅ Better Organization
- All email tasks in one file
- Easy to find and maintain
- Clear separation of concerns

### ✅ Easier Imports
- Single import location: `from accounts.tasks import ...`
- No confusion about where tasks are defined

### ✅ Better Maintainability
- Update tasks in one place
- Easier to add new email tasks
- Consistent structure

### ✅ Cleaner Codebase
- Follows Django best practices
- App-specific tasks in app's tasks.py
- Logical grouping

## Migration Guide

### Old Way (DEPRECATED)
```python
from scrimverse.email_tasks import send_welcome_email_task
```

### New Way (RECOMMENDED)
```python
from accounts.tasks import send_welcome_email_task
```

## Files Updated

1. ✅ `accounts/tasks.py` - Added all 11 email tasks
2. ✅ `accounts/views.py` - Updated imports to use accounts.tasks

## Files to Update (When Integrating Other Emails)

When you integrate other emails, import from `accounts.tasks`:

```python
# tournaments/views.py
from accounts.tasks import (
    send_tournament_registration_email_task,
    send_tournament_created_email_task,
    send_registration_limit_reached_email_task,
    send_tournament_completed_email_task,
)

# Any other view file
from accounts.tasks import send_password_reset_email_task
```

## Task Names (for Celery)

All tasks are registered with their full names:

- `send_welcome_email_task`
- `send_password_reset_email_task`
- `send_password_changed_email_task`
- `send_tournament_registration_email_task`
- `send_tournament_results_email_task`
- `send_premium_tournament_promo_email_task`
- `send_host_approved_email_task`
- `send_tournament_created_email_task`
- `send_tournament_reminder_email_task`
- `send_registration_limit_reached_email_task`
- `send_tournament_completed_email_task`

## Celery Worker

No changes needed! The Celery worker will automatically discover tasks from `accounts/tasks.py`.

Your Celery worker is already running and will pick up these tasks.

## Testing

Test that tasks are working:

```bash
python test_welcome_integration.py
```

Or manually:

```python
from accounts.tasks import send_welcome_email_task

send_welcome_email_task.delay(
    user_email="test@example.com",
    user_name="Test User",
    dashboard_url="http://localhost:3000/dashboard",
    user_type='player'
)
```

## Summary

✅ **All email tasks centralized** in `accounts/tasks.py`
✅ **Views updated** to import from `accounts.tasks`
✅ **No breaking changes** - task names remain the same
✅ **Celery worker** automatically discovers tasks
✅ **Better organization** and maintainability

---

**Status**: Email tasks successfully centralized! ✨

**Next**: Continue integrating other email types using `from accounts.tasks import ...`
