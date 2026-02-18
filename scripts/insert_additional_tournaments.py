#!/usr/bin/env python
"""
Insert additional diverse tournaments for testing
Adds 10 more tournaments with a wider variety of games and modes
"""
import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from tournaments.models import Tournament
from accounts.models import HostProfile

# Get or create a host (use first available host)
host = HostProfile.objects.first()
if not host:
    print("❌ No host profile found. Please create a host account first.")
    sys.exit(1)

# Tournament data with variety
tournaments_data = [
    {
        "title": "Dota 2 5v5 Classic",
        "game_name": "Dota 2",
        "game_mode": "5v5",
        "description": "5v5 Dota 2 tournament with classic rules",
        "entry_fee": 100,
        "max_participants": 20,
        "prize_pool": 10000,
    },
    {
        "title": "Fortnite Solos Free Battle",
        "game_name": "Fortnite",
        "game_mode": "Solo",
        "description": "Solo Fortnite battle royale tournament",
        "entry_fee": 0,
        "max_participants": 100,
        "prize_pool": 5000,
    },
    {
        "title": "Elden Ring PvP Duels",
        "game_name": "Elden Ring",
        "game_mode": "Solo",
        "description": "1v1 PvP duels in Elden Ring",
        "entry_fee": 50,
        "max_participants": 32,
        "prize_pool": 3000,
    },
    {
        "title": "Tekken 8 1v1 Championship",
        "game_name": "Tekken 8",
        "game_mode": "Solo",
        "description": "Fighting game tournament - Best of 3 matches",
        "entry_fee": 75,
        "max_participants": 64,
        "prize_pool": 8000,
    },
    {
        "title": "Rocket League 3v3 League",
        "game_name": "Rocket League",
        "game_mode": "Trio",
        "description": "3v3 Rocket League competitive league",
        "entry_fee": 150,
        "max_participants": 30,
        "prize_pool": 12000,
    },
    {
        "title": "StarCraft 2 1v1 Pro",
        "game_name": "StarCraft 2",
        "game_mode": "Solo",
        "description": "Real-time strategy 1v1 competitive matches",
        "entry_fee": 200,
        "max_participants": 16,
        "prize_pool": 5000,
    },
    {
        "title": "Overwatch 2 5v5 Team Wars",
        "game_name": "Overwatch 2",
        "game_mode": "5v5",
        "description": "Team-based hero shooter tournament",
        "entry_fee": 250,
        "max_participants": 20,
        "prize_pool": 15000,
    },
    {
        "title": "Among Us Social Free",
        "game_name": "Among Us",
        "game_mode": "Squad",
        "description": "Social deduction game - 4-10 players per match",
        "entry_fee": 0,
        "max_participants": 100,
        "prize_pool": 2000,
    },
    {
        "title": "Street Fighter 6 Arcade Edition",
        "game_name": "Street Fighter 6",
        "game_mode": "Solo",
        "description": "Fighting game arcade mode tournament",
        "entry_fee": 80,
        "max_participants": 32,
        "prize_pool": 4000,
    },
    {
        "title": "Helldivers 2 Squad Coop",
        "game_name": "Helldivers 2",
        "game_mode": "Squad",
        "description": "4-player cooperative shooter tournament",
        "entry_fee": 120,
        "max_participants": 40,
        "prize_pool": 8000,
    },
]

# Create tournaments
now = datetime.now()
reg_start = now - timedelta(hours=1)
reg_end = now + timedelta(days=7)
tournament_start = now + timedelta(days=8)
tournament_end = now + timedelta(days=9)

created_ids = []

for data in tournaments_data:
    tournament = Tournament.objects.create(
        host=host,
        title=data["title"],
        game_name=data["game_name"],
        game_mode=data["game_mode"],
        description=data["description"],
        entry_fee=data["entry_fee"],
        max_participants=data["max_participants"],
        prize_pool=data["prize_pool"],
        registration_start=reg_start,
        registration_end=reg_end,
        tournament_start=tournament_start,
        tournament_end=tournament_end,
        status="upcoming",
        rules="Standard tournament rules apply. Check-in required 15 minutes before start.",
    )
    created_ids.append(tournament.id)
    
    fee_str = f"INR {data['entry_fee']}" if data["entry_fee"] > 0 else "FREE"
    print(f"✓ Created: {data['game_name']} {data['game_mode']} ({tournament.id}) {fee_str}")

print(f"\nDone. Created {len(created_ids)} tournaments: {created_ids}")
