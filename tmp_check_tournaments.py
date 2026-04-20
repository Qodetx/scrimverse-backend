import os
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament

tournaments = Tournament.objects.all().values('id', 'title', 'game_name', 'banner_image')
print("ID | Game | Banner | Title")
print("-" * 60)
for t in tournaments:
    print(f"{t['id']} | {t['game_name']} | {t['banner_image']} | {t['title']}")
