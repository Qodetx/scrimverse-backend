# Email Integration Examples for Scrimverse

This document shows exactly where to add email triggers in your existing code.

## 1. Player Registration - Welcome Email

**File**: `accounts/views.py`
**Class**: `PlayerRegistrationView`
**Method**: `create`

```python
from scrimverse.email_tasks import send_welcome_email_task
from django.conf import settings

class PlayerRegistrationView(generics.CreateAPIView):
    # ... existing code ...

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        # ADD THIS: Send welcome email
        if response.status_code == status.HTTP_201_CREATED:
            user_data = response.data.get('user', {})
            send_welcome_email_task.delay(
                user_email=user_data.get('email'),
                user_name=user_data.get('username'),
                dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard"
            )

        return response
```

## 2. Host Registration - Welcome Email

**File**: `accounts/views.py`
**Class**: `HostRegistrationView`
**Method**: `create`

```python
from scrimverse.email_tasks import send_welcome_email_task
from django.conf import settings

class HostRegistrationView(generics.CreateAPIView):
    # ... existing code ...

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        # ADD THIS: Send welcome email
        if response.status_code == status.HTTP_201_CREATED:
            user_data = response.data.get('user', {})
            send_welcome_email_task.delay(
                user_email=user_data.get('email'),
                user_name=user_data.get('username'),
                dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/dashboard"
            )

        return response
```

## 3. Password Reset Request

**File**: `accounts/views.py`
**Find the password reset view** (you may need to create this if using Django's built-in)

```python
from scrimverse.email_tasks import send_password_reset_email_task
from django.conf import settings

# In your password reset view
def request_password_reset(request):
    # ... existing code to generate reset token ...

    # ADD THIS: Send password reset email
    reset_url = f"{settings.CORS_ALLOWED_ORIGINS[0]}/reset-password/{reset_token}"
    send_password_reset_email_task.delay(
        user_email=user.email,
        user_name=user.username,
        reset_url=reset_url
    )
```

## 4. Password Changed Successfully

**File**: `accounts/views.py`
**Find the password change view**

```python
from scrimverse.email_tasks import send_password_changed_email_task
from django.conf import settings
from django.utils import timezone

# In your password change view
def change_password(request):
    # ... existing code to change password ...

    # ADD THIS: Send password changed email
    send_password_changed_email_task.delay(
        user_email=request.user.email,
        user_name=request.user.username,
        changed_at=timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        ip_address=request.META.get('REMOTE_ADDR', 'Unknown'),
        dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard"
    )
```

## 5. Tournament Registration Successful

**File**: `tournaments/views.py`
**Class**: `TournamentRegistrationCreateView`
**Method**: `perform_create`

```python
from scrimverse.email_tasks import send_tournament_registration_email_task
from django.conf import settings

class TournamentRegistrationCreateView(generics.CreateAPIView):
    # ... existing code ...

    def perform_create(self, serializer):
        registration = serializer.save()

        # ... existing code ...

        # ADD THIS: Send registration confirmation email
        tournament = registration.tournament
        send_tournament_registration_email_task.delay(
            user_email=registration.user.email,
            user_name=registration.user.username,
            tournament_name=tournament.name,
            game_name=tournament.game.name,
            start_date=tournament.start_date.strftime("%B %d, %Y at %I:%M %p"),
            registration_id=str(registration.id),
            tournament_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/tournaments/{tournament.id}",
            team_name=registration.team_name
        )
```

## 6. Registration Limit Reached

**File**: `tournaments/views.py`
**Class**: `TournamentRegistrationCreateView`
**Method**: `perform_create`

```python
from scrimverse.email_tasks import send_registration_limit_reached_email_task
from django.conf import settings

class TournamentRegistrationCreateView(generics.CreateAPIView):
    # ... existing code ...

    def perform_create(self, serializer):
        registration = serializer.save()
        tournament = registration.tournament

        # ... existing code ...

        # ADD THIS: Check if registration limit reached
        current_registrations = tournament.registrations.count()
        if current_registrations >= tournament.max_participants:
            send_registration_limit_reached_email_task.delay(
                host_email=tournament.host.user.email,
                host_name=tournament.host.organization_name or tournament.host.user.username,
                tournament_name=tournament.name,
                total_registrations=current_registrations,
                max_participants=tournament.max_participants,
                start_date=tournament.start_date.strftime("%B %d, %Y at %I:%M %p"),
                tournament_manage_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/tournaments/{tournament.id}"
            )
```

## 7. Tournament Created Successfully

**File**: `tournaments/views.py`
**Class**: `TournamentCreateView`
**Method**: `create`

```python
from scrimverse.email_tasks import send_tournament_created_email_task
from django.conf import settings

class TournamentCreateView(generics.CreateAPIView):
    # ... existing code ...

    def create(self, request, *args, **kwargs):
        # ... existing code that creates tournament ...

        # ADD THIS: Send tournament created email (after payment success)
        # This should be added in the payment callback/webhook handler
        # when tournament is actually created after successful payment

        tournament = created_tournament  # Your tournament instance
        send_tournament_created_email_task.delay(
            host_email=tournament.host.user.email,
            host_name=tournament.host.organization_name or tournament.host.user.username,
            tournament_name=tournament.name,
            game_name=tournament.game.name,
            start_date=tournament.start_date.strftime("%B %d, %Y at %I:%M %p"),
            max_participants=tournament.max_participants,
            plan_type=tournament.plan_type.upper(),
            tournament_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/tournaments/{tournament.id}",
            tournament_manage_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/tournaments/{tournament.id}"
        )
```

## 8. Tournament Results Published

**File**: `tournaments/views.py`
**Find the view that publishes results** (likely in a results/standings publish view)

```python
from scrimverse.email_tasks import send_tournament_results_email_task
from django.conf import settings

# In your publish results view
def publish_tournament_results(request, tournament_id):
    tournament = Tournament.objects.get(id=tournament_id)

    # ... existing code to publish results ...

    # ADD THIS: Send results email to all participants
    registrations = tournament.registrations.all()
    for registration in registrations:
        # Get final position from standings
        position = registration.final_position or 0

        send_tournament_results_email_task.delay(
            user_email=registration.user.email,
            user_name=registration.user.username,
            tournament_name=tournament.name,
            position=position,
            total_participants=registrations.count(),
            results_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/tournaments/{tournament.id}/results",
            team_name=registration.team_name
        )
```

## 9. Host Account Approved

**File**: `accounts/admin.py` or wherever host approval happens

```python
from scrimverse.email_tasks import send_host_approved_email_task
from django.conf import settings
from django.utils import timezone

# In admin action or approval view
def approve_host(host_profile):
    host_profile.verification_status = 'approved'
    host_profile.save()

    # ADD THIS: Send approval email
    send_host_approved_email_task.delay(
        user_email=host_profile.user.email,
        user_name=host_profile.user.username,
        host_name=host_profile.organization_name or host_profile.user.username,
        approved_at=timezone.now().strftime("%B %d, %Y at %I:%M %p"),
        host_dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/dashboard"
    )
```

## 10. Tournament Reminder (Same Day) - Celery Scheduled Task

**File**: `tournaments/tasks.py`

```python
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from tournaments.models import Tournament
from scrimverse.email_tasks import send_tournament_reminder_email_task
from django.conf import settings

@shared_task(name="send_tournament_reminders")
def send_tournament_reminders():
    """
    Celery task to send tournament reminders on the day of the tournament
    Schedule this to run every hour or at specific times
    """
    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)

    # Get tournaments starting today that haven't been reminded yet
    tournaments = Tournament.objects.filter(
        start_date__date=today,
        status='upcoming',
        reminder_sent=False  # Add this field to Tournament model
    )

    for tournament in tournaments:
        send_tournament_reminder_email_task.delay(
            host_email=tournament.host.user.email,
            host_name=tournament.host.organization_name or tournament.host.user.username,
            tournament_name=tournament.name,
            start_time=tournament.start_date.strftime("%I:%M %p"),
            total_registrations=tournament.registrations.count(),
            tournament_manage_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/tournaments/{tournament.id}"
        )

        # Mark as reminded
        tournament.reminder_sent = True
        tournament.save()
```

**Add to Celery Beat Schedule** in `scrimverse/celery.py`:

```python
from celery.schedules import crontab

app.conf.beat_schedule = {
    # ... existing schedules ...
    'send-tournament-reminders': {
        'task': 'send_tournament_reminders',
        'schedule': crontab(hour='*/2'),  # Every 2 hours
    },
}
```

## 11. Tournament Completed Summary

**File**: `tournaments/views.py` or `tournaments/tasks.py`

```python
from scrimverse.email_tasks import send_tournament_completed_email_task
from django.conf import settings

# When tournament status changes to completed
def complete_tournament(tournament):
    tournament.status = 'completed'
    tournament.save()

    # Get winner and runner-up
    standings = tournament.get_final_standings()  # Your method to get standings
    winner = standings[0] if len(standings) > 0 else None
    runner_up = standings[1] if len(standings) > 1 else None

    # ADD THIS: Send completion summary email
    send_tournament_completed_email_task.delay(
        host_email=tournament.host.user.email,
        host_name=tournament.host.organization_name or tournament.host.user.username,
        tournament_name=tournament.name,
        completed_at=timezone.now().strftime("%B %d, %Y at %I:%M %p"),
        total_participants=tournament.registrations.count(),
        total_matches=tournament.matches.count() if hasattr(tournament, 'matches') else 0,
        winner_name=winner.team_name if winner else "TBD",
        runner_up_name=runner_up.team_name if runner_up else "TBD",
        total_registrations=tournament.registrations.count(),
        results_published=tournament.results_published if hasattr(tournament, 'results_published') else False,
        tournament_manage_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/tournaments/{tournament.id}"
    )
```

## Important Notes

1. **Always use `.delay()`** - This sends the email asynchronously via Celery
2. **Check Celery is running** - Make sure your Celery worker and beat are running
3. **Test in sandbox mode first** - Use verified emails until production access is approved
4. **Handle errors gracefully** - Email failures shouldn't break your main functionality
5. **Add logging** - Monitor email sending in your logs

## Testing Quick Command

```python
# Django shell
python manage.py shell

from scrimverse.email_tasks import send_welcome_email_task

# Test email (use a verified email in sandbox mode)
send_welcome_email_task.delay(
    user_email="your-verified-email@example.com",
    user_name="Test User",
    dashboard_url="http://localhost:3000/dashboard"
)
```
