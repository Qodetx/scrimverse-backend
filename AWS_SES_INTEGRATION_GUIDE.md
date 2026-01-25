# AWS SES Email Integration Guide for Scrimverse

## Current Status ✅
- Domain verified: scrimverse.com
- DKIM configured: Successful
- MAIL FROM domain: mail.scrimverse.com
- Production access: In process

## Next Steps to Complete Setup

### Step 1: Generate SMTP Credentials

Since your production access is still in process, you have two options:

#### Option A: Use Sandbox Mode (For Testing)
While waiting for production approval, you can test emails in sandbox mode:

1. **Add Verified Email Addresses**:
   - Go to AWS SES Console → Verified identities
   - Click "Create identity"
   - Select "Email address"
   - Add your personal email (e.g., your Gmail)
   - Verify the email by clicking the link sent to your inbox
   - Repeat for any test email addresses

2. **Generate SMTP Credentials**:
   - Go to AWS SES Console
   - Click on "SMTP settings" in the left sidebar
   - Click "Create SMTP credentials"
   - Enter a username (e.g., "scrimverse-smtp-user")
   - Click "Create"
   - **IMPORTANT**: Download and save the credentials (you won't see them again!)
   - Copy the SMTP username and password

3. **Update .env file**:
   ```bash
   EMAIL_HOST_PASSWORD=<your-smtp-password-here>
   ```

#### Option B: Wait for Production Access (Recommended for Live Use)
- Once AWS approves your production access request, you can send emails to any address
- The SMTP credentials generation process is the same
- No need to verify individual recipient emails

### Step 2: Configure SMTP Settings

Your `.env` file is already configured with:
```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=email-smtp.ap-south-2.amazonaws.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=AKIA4VQTC53LRAE7GZQP  # This is your AWS Access Key
EMAIL_HOST_PASSWORD=  # ADD SMTP PASSWORD HERE
DEFAULT_FROM_EMAIL=noreply@scrimverse.com
SUPPORT_EMAIL=support@scrimverse.com
ADMIN_EMAIL=admin@scrimverse.com
```

**Important Notes**:
- `EMAIL_HOST_USER` should be the SMTP username (not your AWS Access Key)
- `EMAIL_HOST_PASSWORD` should be the SMTP password (not your AWS Secret Key)
- These are different from your AWS IAM credentials!

### Step 3: Test Email Sending

Once you've added the SMTP password, test the email functionality:

```bash
# In Django shell
python manage.py shell
```

```python
from scrimverse.email_utils import send_welcome_email

# Test sending a welcome email
send_welcome_email(
    user_email="your-verified-email@example.com",  # Use a verified email in sandbox mode
    user_name="Test User",
    dashboard_url="http://localhost:3000/dashboard"
)
```

### Step 4: Monitor Email Sending

1. **Check AWS SES Console**:
   - Go to "Sending statistics" to see email metrics
   - Monitor bounce and complaint rates

2. **Check Django Logs**:
   - Email sending is logged in `logs/django.log`
   - Check for any errors

## Email Integration Points

The email system is now integrated at these points in your application:

### 1. Account & Security Emails

#### Sign up successful (welcome email)
**File**: `accounts/views.py`
**Trigger**: After user registration
```python
from scrimverse.email_tasks import send_welcome_email_task

# In your registration view
send_welcome_email_task.delay(
    user_email=user.email,
    user_name=user.username,
    dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard"
)
```

#### Password reset request
**File**: `accounts/views.py`
**Trigger**: When user requests password reset
```python
from scrimverse.email_tasks import send_password_reset_email_task

send_password_reset_email_task.delay(
    user_email=user.email,
    user_name=user.username,
    reset_url=reset_link
)
```

#### Password changed successfully
**File**: `accounts/views.py`
**Trigger**: After password change
```python
from scrimverse.email_tasks import send_password_changed_email_task
from django.utils import timezone

send_password_changed_email_task.delay(
    user_email=user.email,
    user_name=user.username,
    changed_at=timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
    ip_address=request.META.get('REMOTE_ADDR', 'Unknown'),
    dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard"
)
```

### 2. Tournament – Player Side Emails

#### Tournament registration successful
**File**: `tournaments/views.py`
**Trigger**: After successful tournament registration
```python
from scrimverse.email_tasks import send_tournament_registration_email_task

send_tournament_registration_email_task.delay(
    user_email=user.email,
    user_name=user.username,
    tournament_name=tournament.name,
    game_name=tournament.game.name,
    start_date=tournament.start_date.strftime("%Y-%m-%d %H:%M"),
    registration_id=str(registration.id),
    tournament_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/tournaments/{tournament.id}",
    team_name=registration.team_name if hasattr(registration, 'team_name') else None
)
```

#### Tournament results published
**File**: `tournaments/views.py`
**Trigger**: When host publishes results
```python
from scrimverse.email_tasks import send_tournament_results_email_task

# Send to all participants
for registration in tournament.registrations.all():
    send_tournament_results_email_task.delay(
        user_email=registration.user.email,
        user_name=registration.user.username,
        tournament_name=tournament.name,
        position=registration.final_position,
        total_participants=tournament.registrations.count(),
        results_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/tournaments/{tournament.id}/results",
        team_name=registration.team_name if hasattr(registration, 'team_name') else None
    )
```

#### Premium tournament promotions
**File**: `tournaments/tasks.py` (Celery scheduled task)
**Trigger**: Scheduled task for premium tournament promotions
```python
from scrimverse.email_tasks import send_premium_tournament_promo_email_task

# Send to active players
for player in active_players:
    send_premium_tournament_promo_email_task.delay(
        user_email=player.email,
        user_name=player.username,
        tournament_name=tournament.name,
        game_name=tournament.game.name,
        prize_pool=f"₹{tournament.prize_pool}",
        registration_deadline=tournament.registration_deadline.strftime("%Y-%m-%d"),
        start_date=tournament.start_date.strftime("%Y-%m-%d %H:%M"),
        tournament_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/tournaments/{tournament.id}"
    )
```

### 3. Tournament – Host Side Emails

#### Host account approved
**File**: `accounts/admin.py` or `accounts/views.py`
**Trigger**: When admin approves host account
```python
from scrimverse.email_tasks import send_host_approved_email_task
from django.utils import timezone

send_host_approved_email_task.delay(
    user_email=host.user.email,
    user_name=host.user.username,
    host_name=host.organization_name or host.user.username,
    approved_at=timezone.now().strftime("%Y-%m-%d %H:%M"),
    host_dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/dashboard"
)
```

#### Tournament created successfully
**File**: `tournaments/views.py`
**Trigger**: After tournament creation
```python
from scrimverse.email_tasks import send_tournament_created_email_task

send_tournament_created_email_task.delay(
    host_email=tournament.host.user.email,
    host_name=tournament.host.organization_name or tournament.host.user.username,
    tournament_name=tournament.name,
    game_name=tournament.game.name,
    start_date=tournament.start_date.strftime("%Y-%m-%d %H:%M"),
    max_participants=tournament.max_participants,
    plan_type=tournament.plan_type,
    tournament_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/tournaments/{tournament.id}",
    tournament_manage_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/tournaments/{tournament.id}"
)
```

#### Tournament reminder (same day)
**File**: `tournaments/tasks.py` (Celery scheduled task)
**Trigger**: Scheduled task on tournament day
```python
from scrimverse.email_tasks import send_tournament_reminder_email_task

send_tournament_reminder_email_task.delay(
    host_email=tournament.host.user.email,
    host_name=tournament.host.organization_name or tournament.host.user.username,
    tournament_name=tournament.name,
    start_time=tournament.start_date.strftime("%H:%M"),
    total_registrations=tournament.registrations.count(),
    tournament_manage_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/tournaments/{tournament.id}"
)
```

#### Registrations limit reached
**File**: `tournaments/views.py`
**Trigger**: When registration count reaches max_participants
```python
from scrimverse.email_tasks import send_registration_limit_reached_email_task

# Check after each registration
if tournament.registrations.count() >= tournament.max_participants:
    send_registration_limit_reached_email_task.delay(
        host_email=tournament.host.user.email,
        host_name=tournament.host.organization_name or tournament.host.user.username,
        tournament_name=tournament.name,
        total_registrations=tournament.registrations.count(),
        max_participants=tournament.max_participants,
        start_date=tournament.start_date.strftime("%Y-%m-%d %H:%M"),
        tournament_manage_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/tournaments/{tournament.id}"
    )
```

#### Tournament completed summary
**File**: `tournaments/views.py` or `tournaments/tasks.py`
**Trigger**: When tournament status changes to completed
```python
from scrimverse.email_tasks import send_tournament_completed_email_task

# Get winner and runner-up
standings = tournament.get_final_standings()
winner = standings[0] if len(standings) > 0 else None
runner_up = standings[1] if len(standings) > 1 else None

send_tournament_completed_email_task.delay(
    host_email=tournament.host.user.email,
    host_name=tournament.host.organization_name or tournament.host.user.username,
    tournament_name=tournament.name,
    completed_at=tournament.end_date.strftime("%Y-%m-%d %H:%M"),
    total_participants=tournament.registrations.count(),
    total_matches=tournament.matches.count(),
    winner_name=winner.team_name if winner else "TBD",
    runner_up_name=runner_up.team_name if runner_up else "TBD",
    total_registrations=tournament.registrations.count(),
    results_published=tournament.results_published,
    tournament_manage_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/tournaments/{tournament.id}"
)
```

## Important Notes

### Sandbox Mode Limitations
- Can only send to verified email addresses
- Max 200 emails per 24 hours
- Max 1 email per second

### Production Mode Benefits
- Send to any email address
- Higher sending limits (starts at 50,000/day)
- Better deliverability

### Best Practices
1. Always use `.delay()` for Celery tasks to send emails asynchronously
2. Monitor bounce and complaint rates in AWS SES console
3. Keep email templates professional and concise
4. Include unsubscribe links for promotional emails
5. Test emails thoroughly in sandbox mode before going to production

## Troubleshooting

### Email not sending?
1. Check `.env` file has correct SMTP credentials
2. Verify Celery worker is running
3. Check Django logs for errors
4. Verify recipient email is verified (in sandbox mode)

### SMTP Authentication Error?
- Make sure you're using SMTP credentials, not AWS IAM credentials
- Regenerate SMTP credentials if needed

### Emails going to spam?
- Ensure DKIM and SPF records are properly configured
- Use a professional email template
- Avoid spam trigger words
- Maintain low bounce/complaint rates

## Testing Checklist

- [ ] Generate SMTP credentials from AWS SES
- [ ] Update EMAIL_HOST_PASSWORD in .env
- [ ] Verify test email addresses (sandbox mode)
- [ ] Test welcome email
- [ ] Test password reset email
- [ ] Test tournament registration email
- [ ] Test host approval email
- [ ] Monitor AWS SES console for delivery
- [ ] Check Django logs for errors
- [ ] Wait for production access approval
- [ ] Test with unverified emails (after production approval)

## Need Help?

If you encounter any issues:
1. Check AWS SES console for error messages
2. Review Django logs in `logs/django.log`
3. Verify Celery worker is running and processing tasks
4. Test with AWS SES sandbox verified emails first
