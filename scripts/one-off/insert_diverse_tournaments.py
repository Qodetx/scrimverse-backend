#!/usr/bin/env python
"""
Insert 10 diverse tournaments for testing various scenarios.
"""
import os
import sys
import django
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
sys.path.insert(0, os.path.dirname(__file__).replace('scripts', ''))
django.setup()

from django.utils import timezone
from tournaments.models import Tournament
from accounts.models import HostProfile

# Get default host
try:
    host = HostProfile.objects.get(id=1)
except HostProfile.DoesNotExist:
    print("❌ Host profile with ID 1 not found")
    sys.exit(1)

now = timezone.now()
base_start = now + timedelta(days=3)

tournaments_data = [
    # Free tournaments (no entry fee)
    {
        "title": "BGMI Solo Free Battle",
        "game_name": "BGMI",
        "game_mode": "Solo",
        "max_participants": 100,
        "entry_fee": 0,
        "prize_pool": 5000,
        "description": "Free-for-all BGMI solo tournament",
    },
    # Paid tournaments
    {
        "title": "BGMI Squad Paid Tournament",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "max_participants": 32,
        "entry_fee": 150,
        "prize_pool": 25000,
        "description": "Competitive 4v4 Squad tournament with entry fee",
    },
    {
        "title": "Valorant 5v5 Championship",
        "game_name": "Valorant",
        "game_mode": "5v5",
        "max_participants": 40,
        "entry_fee": 200,
        "prize_pool": 50000,
        "description": "Premium Valorant competitive tournament",
    },
    {
        "title": "COD Warzone Duos Free",
        "game_name": "Call of Duty",
        "game_mode": "Duo",
        "max_participants": 50,
        "entry_fee": 0,
        "prize_pool": 8000,
        "description": "Free COD Warzone 2v2 duos tournament",
    },
    {
        "title": "CSGO 5v5 Pro League",
        "game_name": "CS:GO",
        "game_mode": "5v5",
        "max_participants": 24,
        "entry_fee": 300,
        "prize_pool": 75000,
        "description": "Professional CSGO tournament with high entry fee",
    },
    {
        "title": "PUBG Mobile Squad Friendly",
        "game_name": "PUBG Mobile",
        "game_mode": "Squad",
        "max_participants": 64,
        "entry_fee": 50,
        "prize_pool": 15000,
        "description": "Friendly PUBG Mobile squad tournament",
    },
    {
        "title": "Free Fire Duo Challenge",
        "game_name": "Free Fire",
        "game_mode": "Duo",
        "max_participants": 80,
        "entry_fee": 0,
        "prize_pool": 10000,
        "description": "Free Fire duos - free entry, big pool",
    },
    {
        "title": "Apex Legends Trio Paid",
        "game_name": "Apex Legends",
        "game_mode": "Squad",
        "max_participants": 36,
        "entry_fee": 250,
        "prize_pool": 45000,
        "description": "Apex trios with premium entry",
    },
    {
        "title": "Rainbow Six Siege 5v5",
        "game_name": "Rainbow Six Siege",
        "game_mode": "5v5",
        "max_participants": 20,
        "entry_fee": 400,
        "prize_pool": 80000,
        "description": "Competitive Rainbow Six Siege tournament",
    },
    {
        "title": "Minecraft Bedwars Free",
        "game_name": "Minecraft",
        "game_mode": "Squad",
        "max_participants": 48,
        "entry_fee": 0,
        "prize_pool": 5000,
        "description": "Fun Minecraft Bedwars tournament - free entry",
    },
]

created_ids = []

for idx, data in enumerate(tournaments_data, start=1):
    try:
        tournament = Tournament.objects.create(
            title=data["title"],
            game_name=data["game_name"],
            game_mode=data["game_mode"],
            max_participants=data["max_participants"],
            entry_fee=data["entry_fee"],
            prize_pool=data["prize_pool"],
            description=data["description"],
            host=host,
            registration_start=now - timedelta(hours=1),  # Open now
            registration_end=now + timedelta(days=7),
            tournament_start=base_start,
            tournament_end=base_start + timedelta(hours=4),
            status="upcoming",
            event_mode="TOURNAMENT",
            plan_type="BASIC",
            current_participants=0,
        )
        created_ids.append(tournament.id)
        fee_str = f"₹{data['entry_fee']}" if data['entry_fee'] > 0 else "FREE"
        print(f"✓ Created: {data['title']} (id={tournament.id}) {data['game_mode']} {fee_str}")
    except Exception as e:
        print(f"❌ Failed to create {data['title']}: {e}")

print(f"\n✅ Done. Created {len(created_ids)} tournaments: {created_ids}")
