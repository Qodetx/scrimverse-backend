import os
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament

# Mapping game names to relative banner paths
BANNER_MAPPING = {
    "BGMI": "tournaments/banners/banner-bgmi-tournament.jpg",
    "COD": "tournaments/banners/game-cod.jpg",
    "Call of Duty": "tournaments/banners/game-cod.jpg",
    "Valorant": "tournaments/banners/hero-valorant.jpg",
    "Freefire": "tournaments/banners/banner-freefire-tournament.jpg",
    "Scarfall": "tournaments/banners/banner-scarfall-tournament.jpg",
}

print("Starting banner image updates...")
print("-" * 60)

updated_count = 0
for game, banner_path in BANNER_MAPPING.items():
    tournaments = Tournament.objects.filter(game_name=game)
    count = tournaments.count()
    if count > 0:
        tournaments.update(banner_image=banner_path)
        print(f"Updated {count} tournaments for game: {game} to {banner_path}")
        updated_count += count

print("-" * 60)
print(f"Finished. Total tournaments updated: {updated_count}")
