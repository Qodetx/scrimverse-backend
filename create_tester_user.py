import os
import django
from django.contrib.auth import get_user_model

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

User = get_user_model()
from accounts.models import PlayerProfile

email = 'tester@scrimverse.com'
username = 'tester_player'
password = 'Password123!'
phone = '9999999999'

user, created = User.objects.get_or_create(
    email=email,
    defaults={
        'username': username,
        'user_type': 'player',
        'phone_number': phone,
        'is_email_verified': True,
        'is_active': True
    }
)

if created:
    user.set_password(password)
    user.save()
    PlayerProfile.objects.get_or_create(user=user)
    print(f"User {username} created successfully.")
else:
    user.set_password(password)
    user.is_email_verified = True
    user.is_active = True
    user.save()
    PlayerProfile.objects.get_or_create(user=user)
    print(f"User {username} already existed, password updated and verified.")
