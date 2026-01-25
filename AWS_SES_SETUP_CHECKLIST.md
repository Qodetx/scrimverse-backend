# AWS SES Setup - Step-by-Step Checklist

## ✅ Completed Steps

- [x] Domain verified (scrimverse.com)
- [x] DKIM configuration successful
- [x] MAIL FROM domain configured (mail.scrimverse.com)
- [x] Production access request submitted
- [x] Email templates created
- [x] Email utility functions created
- [x] Celery tasks for async email sending created
- [x] Django settings configured

## 🔄 Next Steps (Do These Now)

### Step 1: Generate SMTP Credentials (5 minutes)

1. Go to AWS SES Console: https://console.aws.amazon.com/ses/
2. Click on "SMTP settings" in the left sidebar
3. Click "Create SMTP credentials" button
4. Enter username: `scrimverse-smtp-user`
5. Click "Create"
6. **IMPORTANT**: Download the credentials CSV file
7. Copy the SMTP username and password

### Step 2: Update .env File (2 minutes)

1. Open: `scrimverse-backend/.env`
2. Find line 52: `EMAIL_HOST_PASSWORD=`
3. Replace line 51 with the SMTP username from Step 1
4. Replace line 52 with the SMTP password from Step 1

```bash
EMAIL_HOST_USER=<SMTP_USERNAME_FROM_AWS>
EMAIL_HOST_PASSWORD=<SMTP_PASSWORD_FROM_AWS>
```

### Step 3: Verify Test Email Address (3 minutes)

**While in Sandbox Mode**, you can only send to verified emails:

1. Go to AWS SES Console → Verified identities
2. Click "Create identity"
3. Select "Email address"
4. Enter your personal email (e.g., your Gmail)
5. Click "Create identity"
6. Check your email inbox
7. Click the verification link
8. Repeat for any other test emails you want to use

### Step 4: Test Email Sending (5 minutes)

1. Make sure Celery worker is running (you already have it running!)
2. Open Django shell:
   ```bash
   python manage.py shell
   ```

3. Run this test:
   ```python
   from scrimverse.email_tasks import send_welcome_email_task

   # Replace with your verified email from Step 3
   send_welcome_email_task.delay(
       user_email="your-verified-email@example.com",
       user_name="Test User",
       dashboard_url="http://localhost:3000/dashboard"
   )
   ```

4. Check your email inbox (might take 1-2 minutes)
5. Check Celery worker logs for any errors

### Step 5: Monitor in AWS Console (2 minutes)

1. Go to AWS SES Console → "Sending statistics"
2. You should see 1 email sent
3. Check for any bounces or complaints (should be 0)

## 🎯 After Production Access is Approved

### Step 6: Remove Sandbox Limitations

Once AWS approves your production access request:

1. You can send to ANY email address (no verification needed)
2. Higher sending limits (50,000 emails/day to start)
3. Better deliverability

### Step 7: Integrate Email Triggers in Code

Use the `EMAIL_INTEGRATION_EXAMPLES.md` file to add email triggers to your views.

**Priority Order**:
1. ✅ Welcome email (Player & Host registration)
2. ✅ Tournament registration confirmation
3. ✅ Host account approved
4. ✅ Tournament created
5. ✅ Password reset & changed
6. ✅ Registration limit reached
7. ✅ Tournament results published
8. ✅ Tournament reminder (Celery task)
9. ✅ Tournament completed summary
10. ✅ Premium tournament promotions

### Step 8: Add Reminder Field to Tournament Model (Optional)

If you want to track tournament reminders:

```python
# In tournaments/models.py
class Tournament(models.Model):
    # ... existing fields ...
    reminder_sent = models.BooleanField(default=False)
```

Then run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

## 📊 Current Email Templates Available

1. ✅ `welcome.html` - Welcome email after signup
2. ✅ `password_reset.html` - Password reset request
3. ✅ `password_changed.html` - Password changed confirmation
4. ✅ `tournament_registration.html` - Tournament registration confirmation
5. ✅ `tournament_results.html` - Tournament results published
6. ✅ `premium_tournament_promo.html` - Premium tournament promotion
7. ✅ `host_approved.html` - Host account approved
8. ✅ `tournament_created.html` - Tournament created successfully
9. ✅ `tournament_reminder.html` - Tournament starting today
10. ✅ `registration_limit_reached.html` - Registration limit reached
11. ✅ `tournament_completed.html` - Tournament completed summary

## 🔍 Troubleshooting

### Email not sending?
- [ ] Check `.env` has correct SMTP credentials
- [ ] Verify Celery worker is running
- [ ] Check `logs/django.log` for errors
- [ ] Verify recipient email is verified (sandbox mode)
- [ ] Check AWS SES Console for errors

### SMTP Authentication Error?
- [ ] Make sure you're using SMTP credentials (not AWS IAM credentials)
- [ ] Regenerate SMTP credentials if needed
- [ ] Check EMAIL_HOST is correct: `email-smtp.ap-south-2.amazonaws.com`

### Emails going to spam?
- [ ] DKIM is configured ✅ (you already have this)
- [ ] SPF record is configured
- [ ] Use professional email content
- [ ] Avoid spam trigger words

## 📝 Quick Reference

### Email Service Functions
Located in: `scrimverse/email_utils.py`

### Celery Tasks
Located in: `scrimverse/email_tasks.py`

### Email Templates
Located in: `templates/emails/`

### Integration Examples
See: `EMAIL_INTEGRATION_EXAMPLES.md`

### Full Setup Guide
See: `AWS_SES_INTEGRATION_GUIDE.md`

## 🎉 Success Criteria

You'll know everything is working when:
- [ ] Test email received in inbox
- [ ] No errors in Celery worker logs
- [ ] AWS SES shows email sent successfully
- [ ] Email doesn't go to spam
- [ ] Production access approved by AWS

## 📞 Support

If you need help:
1. Check Django logs: `logs/django.log`
2. Check Celery logs in terminal
3. Check AWS SES Console → Sending statistics
4. Review error messages carefully

---

**Current Status**: Ready to generate SMTP credentials and test!

**Next Action**: Follow Step 1 above to generate SMTP credentials from AWS SES Console.
