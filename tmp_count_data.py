import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()
from accounts.models import User
from tournaments.models import Tournament
print(f"Users: {User.objects.count()}")
print(f"Tournaments: {Tournament.objects.count()}")
