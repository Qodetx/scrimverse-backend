# Scrimverse Email System Architecture

## Email Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER ACTIONS                                 │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DJANGO VIEWS/SIGNALS                            │
│  • PlayerRegistrationView                                            │
│  • HostRegistrationView                                              │
│  • TournamentRegistrationCreateView                                  │
│  • Password Reset/Change Views                                       │
│  • Tournament Status Changes                                         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CELERY TASKS (Async)                              │
│  scrimverse/email_tasks.py                                           │
│  • send_welcome_email_task.delay()                                   │
│  • send_tournament_registration_email_task.delay()                   │
│  • send_host_approved_email_task.delay()                             │
│  • ... and 8 more tasks                                              │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    EMAIL UTILITY FUNCTIONS                           │
│  scrimverse/email_utils.py                                           │
│  • EmailService.send_email()                                         │
│  • Renders HTML templates                                            │
│  • Creates plain text version                                        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    EMAIL TEMPLATES                                   │
│  templates/emails/                                                   │
│  • base.html (shared layout)                                         │
│  • welcome.html                                                      │
│  • tournament_registration.html                                      │
│  • ... and 9 more templates                                          │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DJANGO EMAIL BACKEND                              │
│  django.core.mail.backends.smtp.EmailBackend                         │
│  • Connects to AWS SES SMTP                                          │
│  • Sends HTML + Plain Text                                           │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS SES                                      │
│  email-smtp.ap-south-2.amazonaws.com:587                             │
│  • DKIM Signing ✅                                                   │
│  • MAIL FROM: mail.scrimverse.com ✅                                 │
│  • Domain: scrimverse.com ✅                                         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RECIPIENT INBOX                                   │
│  📧 Email delivered!                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Email Trigger Points

### 1. Account & Security Emails

```
Player/Host Registration
    ↓
PlayerRegistrationView.create() / HostRegistrationView.create()
    ↓
send_welcome_email_task.delay()
    ↓
📧 Welcome Email

Password Reset Request
    ↓
Password Reset View
    ↓
send_password_reset_email_task.delay()
    ↓
📧 Password Reset Email

Password Changed
    ↓
Password Change View
    ↓
send_password_changed_email_task.delay()
    ↓
📧 Password Changed Confirmation
```

### 2. Tournament - Player Side

```
Tournament Registration
    ↓
TournamentRegistrationCreateView.perform_create()
    ↓
send_tournament_registration_email_task.delay()
    ↓
📧 Registration Confirmation

Results Published
    ↓
Publish Results View
    ↓
Loop through all participants
    ↓
send_tournament_results_email_task.delay() (for each)
    ↓
📧 Results Email (to all participants)

Premium Tournament Created
    ↓
Celery Scheduled Task
    ↓
send_premium_tournament_promo_email_task.delay()
    ↓
📧 Premium Tournament Promo
```

### 3. Tournament - Host Side

```
Host Account Approved
    ↓
Admin Action / Approval View
    ↓
send_host_approved_email_task.delay()
    ↓
📧 Host Approved Email

Tournament Created
    ↓
TournamentCreateView.create() (after payment success)
    ↓
send_tournament_created_email_task.delay()
    ↓
📧 Tournament Created Confirmation

Tournament Day
    ↓
Celery Beat Schedule (every 2 hours)
    ↓
send_tournament_reminder_email_task.delay()
    ↓
📧 Tournament Reminder

Registration Limit Reached
    ↓
TournamentRegistrationCreateView.perform_create()
    ↓
Check: registrations >= max_participants
    ↓
send_registration_limit_reached_email_task.delay()
    ↓
📧 Registration Full Email

Tournament Completed
    ↓
Tournament Status Change to 'completed'
    ↓
send_tournament_completed_email_task.delay()
    ↓
📧 Tournament Summary Email
```

## Technology Stack

```
┌──────────────────────────────────────────────────────────┐
│  Frontend (React)                                         │
│  • User actions trigger API calls                        │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  Backend (Django REST Framework)                          │
│  • Views handle requests                                  │
│  • Trigger Celery tasks                                   │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  Celery (Task Queue)                                      │
│  • Worker: Processes email tasks                          │
│  • Beat: Scheduled tasks (reminders, promos)              │
│  • Broker: Redis                                          │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  Email Service (AWS SES)                                  │
│  • SMTP: email-smtp.ap-south-2.amazonaws.com              │
│  • Port: 587 (TLS)                                        │
│  • Authentication: SMTP credentials                       │
└──────────────────────────────────────────────────────────┘
```

## Configuration Files

```
.env
├── EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
├── EMAIL_HOST=email-smtp.ap-south-2.amazonaws.com
├── EMAIL_PORT=587
├── EMAIL_USE_TLS=True
├── EMAIL_HOST_USER=<SMTP_USERNAME>
├── EMAIL_HOST_PASSWORD=<SMTP_PASSWORD>
├── DEFAULT_FROM_EMAIL=noreply@scrimverse.com
├── SUPPORT_EMAIL=support@scrimverse.com
└── ADMIN_EMAIL=admin@scrimverse.com

scrimverse/settings.py
├── TEMPLATES['DIRS'] = [BASE_DIR / "templates"]
├── EMAIL_BACKEND = config("EMAIL_BACKEND", ...)
├── EMAIL_HOST = config("EMAIL_HOST", ...)
├── EMAIL_PORT = config("EMAIL_PORT", ...)
├── EMAIL_USE_TLS = config("EMAIL_USE_TLS", ...)
└── ... (email configuration)

scrimverse/celery.py
├── CELERY_BROKER_URL = REDIS_URL
├── CELERY_RESULT_BACKEND = REDIS_URL
└── beat_schedule (for scheduled tasks)
```

## File Structure

```
scrimverse-backend/
├── templates/
│   └── emails/
│       ├── base.html                          (Base template)
│       ├── welcome.html                       (Welcome email)
│       ├── password_reset.html                (Password reset)
│       ├── password_changed.html              (Password changed)
│       ├── tournament_registration.html       (Registration confirmation)
│       ├── tournament_results.html            (Results published)
│       ├── premium_tournament_promo.html      (Premium promo)
│       ├── host_approved.html                 (Host approved)
│       ├── tournament_created.html            (Tournament created)
│       ├── tournament_reminder.html           (Tournament reminder)
│       ├── registration_limit_reached.html    (Registration full)
│       └── tournament_completed.html          (Tournament completed)
│
├── scrimverse/
│   ├── email_utils.py                         (Email service functions)
│   ├── email_tasks.py                         (Celery tasks)
│   ├── settings.py                            (Email configuration)
│   └── celery.py                              (Celery configuration)
│
├── accounts/
│   └── views.py                               (Trigger points for account emails)
│
├── tournaments/
│   ├── views.py                               (Trigger points for tournament emails)
│   └── tasks.py                               (Scheduled tasks)
│
├── .env                                       (Email credentials)
├── AWS_SES_SETUP_CHECKLIST.md                (Setup checklist)
├── AWS_SES_INTEGRATION_GUIDE.md              (Detailed guide)
└── EMAIL_INTEGRATION_EXAMPLES.md             (Code examples)
```

## Email Types Summary

| Email Type | Trigger | Recipient | Template |
|------------|---------|-----------|----------|
| Welcome Email | User registration | Player/Host | welcome.html |
| Password Reset | Reset request | User | password_reset.html |
| Password Changed | Password change | User | password_changed.html |
| Tournament Registration | Player registers | Player | tournament_registration.html |
| Tournament Results | Results published | All participants | tournament_results.html |
| Premium Promo | Scheduled task | Active players | premium_tournament_promo.html |
| Host Approved | Admin approval | Host | host_approved.html |
| Tournament Created | Tournament creation | Host | tournament_created.html |
| Tournament Reminder | Same day (scheduled) | Host | tournament_reminder.html |
| Registration Full | Limit reached | Host | registration_limit_reached.html |
| Tournament Completed | Tournament ends | Host | tournament_completed.html |

## Monitoring & Logging

```
Django Logs
├── logs/django.log              (General logs)
├── logs/django_error.log        (Error logs)
└── logs/celery.log              (Celery task logs)

AWS SES Console
├── Sending statistics           (Email metrics)
├── Bounce rate                  (Failed deliveries)
├── Complaint rate               (Spam reports)
└── Reputation dashboard         (Overall health)

Celery Worker Terminal
├── Task execution logs
├── Success/failure status
└── Error messages
```

## Best Practices

1. **Always use `.delay()`** for async execution
2. **Test in sandbox mode** with verified emails first
3. **Monitor AWS SES metrics** regularly
4. **Keep templates professional** and mobile-responsive
5. **Handle failures gracefully** - don't break main flow
6. **Log all email events** for debugging
7. **Use meaningful subject lines**
8. **Include unsubscribe links** for promotional emails
9. **Maintain low bounce/complaint rates** (<5%)
10. **Wait for production access** before sending to all users

---

**Status**: System ready, waiting for SMTP credentials to be configured!
