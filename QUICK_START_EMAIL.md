# 🚀 Quick Start Guide - AWS SES Email Integration

## What's Been Done ✅

I've set up a complete email system for Scrimverse with:

- ✅ **11 Professional Email Templates** (HTML + Plain Text)
- ✅ **Email Service Functions** (scrimverse/email_utils.py)
- ✅ **Celery Tasks** for async sending (scrimverse/email_tasks.py)
- ✅ **Django Configuration** (settings.py + .env)
- ✅ **Test Script** (test_emails.py)
- ✅ **Complete Documentation** (4 guide files)

## What You Need to Do Now 🎯

### 1. Generate SMTP Credentials (5 minutes)

**Go to AWS SES Console**: https://console.aws.amazon.com/ses/

1. Click **"SMTP settings"** (left sidebar)
2. Click **"Create SMTP credentials"**
3. Username: `scrimverse-smtp-user`
4. Click **"Create"**
5. **Download the CSV file** (IMPORTANT!)
6. Copy the username and password

### 2. Update .env File (2 minutes)

Open `scrimverse-backend/.env` and update these lines:

```bash
# Line 51-52 - Replace with your SMTP credentials from Step 1
EMAIL_HOST_USER=<YOUR_SMTP_USERNAME>
EMAIL_HOST_PASSWORD=<YOUR_SMTP_PASSWORD>
```

### 3. Verify Test Email (3 minutes)

**While in Sandbox Mode**, verify your email:

1. AWS SES Console → **Verified identities**
2. Click **"Create identity"**
3. Select **"Email address"**
4. Enter your email (e.g., your Gmail)
5. Click **"Create identity"**
6. Check your inbox and click the verification link

### 4. Test the System (5 minutes)

Run the test script:

```bash
cd scrimverse-backend
python test_emails.py your-verified-email@example.com
```

This will send 11 test emails. Check your inbox!

## Email Types Implemented

### Account & Security (3 emails)
1. ✅ Welcome email (signup)
2. ✅ Password reset request
3. ✅ Password changed confirmation

### Tournament - Player Side (3 emails)
4. ✅ Tournament registration confirmation
5. ✅ Tournament results published
6. ✅ Premium tournament promotions

### Tournament - Host Side (5 emails)
7. ✅ Host account approved
8. ✅ Tournament created successfully
9. ✅ Tournament reminder (same day)
10. ✅ Registration limit reached
11. ✅ Tournament completed summary

## How to Integrate Emails in Your Code

### Example 1: Send Welcome Email After Registration

```python
# In accounts/views.py - PlayerRegistrationView.create()
from scrimverse.email_tasks import send_welcome_email_task
from django.conf import settings

def create(self, request, *args, **kwargs):
    response = super().create(request, *args, **kwargs)

    if response.status_code == status.HTTP_201_CREATED:
        user_data = response.data.get('user', {})
        send_welcome_email_task.delay(
            user_email=user_data.get('email'),
            user_name=user_data.get('username'),
            dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard"
        )

    return response
```

### Example 2: Send Registration Confirmation

```python
# In tournaments/views.py - TournamentRegistrationCreateView.perform_create()
from scrimverse.email_tasks import send_tournament_registration_email_task
from django.conf import settings

def perform_create(self, serializer):
    registration = serializer.save()
    tournament = registration.tournament

    # Send confirmation email
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

**See `EMAIL_INTEGRATION_EXAMPLES.md` for all 11 integration examples!**

## Important Files

| File | Purpose |
|------|---------|
| `AWS_SES_SETUP_CHECKLIST.md` | Step-by-step setup checklist |
| `AWS_SES_INTEGRATION_GUIDE.md` | Detailed integration guide |
| `EMAIL_INTEGRATION_EXAMPLES.md` | Code examples for all emails |
| `EMAIL_SYSTEM_ARCHITECTURE.md` | System architecture diagram |
| `test_emails.py` | Test all email templates |
| `scrimverse/email_utils.py` | Email service functions |
| `scrimverse/email_tasks.py` | Celery async tasks |
| `templates/emails/` | HTML email templates |

## Sandbox vs Production Mode

### Sandbox Mode (Current)
- ✅ Domain verified
- ✅ DKIM configured
- ⏳ Production access pending
- ⚠️ Can only send to verified emails
- ⚠️ Max 200 emails/day

### Production Mode (After Approval)
- ✅ Send to ANY email
- ✅ 50,000 emails/day
- ✅ Better deliverability
- ✅ No verification needed

## Troubleshooting

### "SMTP Authentication Failed"
- Make sure you're using **SMTP credentials** (not AWS Access Keys)
- Regenerate credentials if needed

### "Email not received"
- Check if email is verified (sandbox mode)
- Check spam folder
- Check AWS SES Console → Sending statistics
- Check Django logs: `logs/django.log`

### "Celery task not executing"
- Make sure Celery worker is running
- Check Celery logs in terminal
- Try synchronous send for testing:
  ```python
  from scrimverse.email_utils import send_welcome_email
  send_welcome_email(...)  # Without .delay()
  ```

## Next Steps

1. ✅ Generate SMTP credentials
2. ✅ Update .env file
3. ✅ Verify test email
4. ✅ Run test script
5. ✅ Check inbox for 11 emails
6. ✅ Integrate emails in your views (see examples)
7. ⏳ Wait for production access approval
8. ✅ Start sending to all users!

## Quick Commands

```bash
# Test all emails
python test_emails.py your-email@example.com

# Test single email in Django shell
python manage.py shell
>>> from scrimverse.email_utils import send_welcome_email
>>> send_welcome_email("test@example.com", "Test User", "http://localhost:3000/dashboard")

# Check Celery worker status
# (Should already be running in your terminal)

# View Django logs
cat logs/django.log

# View Celery logs
# Check the terminal where Celery worker is running
```

## Support Resources

- **AWS SES Console**: https://console.aws.amazon.com/ses/
- **AWS SES Documentation**: https://docs.aws.amazon.com/ses/
- **Django Email Documentation**: https://docs.djangoproject.com/en/5.0/topics/email/
- **Celery Documentation**: https://docs.celeryproject.org/

## Summary

You now have a **production-ready email system** with:
- 11 professional email templates
- Async sending via Celery
- AWS SES integration
- Complete documentation
- Test scripts

**All you need to do is:**
1. Generate SMTP credentials from AWS
2. Update .env file
3. Test with verified email
4. Integrate in your views

That's it! 🎉

---

**Questions?** Check the detailed guides or review the code comments.

**Ready to test?** Run: `python test_emails.py your-email@example.com`
