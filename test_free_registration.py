#!/usr/bin/env python
"""
Test free tournament registration with detailed logging.
Run this to test the complete free registration flow on tournament 33.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
import json

User = get_user_model()

# Get or create test player
try:
    player_user = User.objects.get(username='testplayer')
except User.DoesNotExist:
    player_user = User.objects.create_user(
        username='testplayer',
        email='testplayer@example.com',
        password='testpass123',
        user_type='player'
    )
    from accounts.models import PlayerProfile
    PlayerProfile.objects.get_or_create(user=player_user)
    print(f"Created test player user: {player_user.username}")

# Create test client
client = Client()

# Login
login_success = client.login(username='testplayer', password='testpass123')
print(f"Login successful: {login_success}")

# Prepare registration data
tournament_id = 33
team_name = "Test Free Team"
# Use emails that are likely unregistered
teammate_emails = [
    'unregistered1@example.com',
    'unregistered2@example.com',
]

data = {
    'team_name': team_name,
    'teammate_emails': teammate_emails,
}

print(f"\n{'='*70}")
print(f"Testing FREE TOURNAMENT Registration")
print(f"{'='*70}")
print(f"Tournament ID: {tournament_id}")
print(f"Team Name: {team_name}")
print(f"Teammate Emails: {teammate_emails}")
print(f"{'='*70}\n")

# Call register-init endpoint
response = client.post(
    f'/api/tournaments/{tournament_id}/register-init/',
    data=json.dumps(data),
    content_type='application/json'
)

print(f"Response Status: {response.status_code}")
print(f"Response Data:")
print(json.dumps(response.json(), indent=2))

# Check database state
from tournaments.models import TournamentRegistration
from accounts.models import TeamJoinRequest

print(f"\n{'='*70}")
print("Database Check")
print(f"{'='*70}\n")

# Find the latest registration
registration = TournamentRegistration.objects.filter(
    tournament_id=tournament_id,
    player__user__username='testplayer'
).order_by('-id').first()

if registration:
    print(f"✓ Registration found: ID={registration.id}")
    print(f"  - Status: {registration.status}")
    print(f"  - Payment Status: {registration.payment_status}")
    print(f"  - Team Name: {registration.team_name}")
    
    # Check team join requests
    team_join_requests = TeamJoinRequest.objects.filter(
        tournament_registration=registration
    )
    print(f"\nTeam Join Requests: {team_join_requests.count()}")
    for tjr in team_join_requests:
        print(f"  - ID={tjr.id}, Email={tjr.invited_email}, Status={tjr.status}, Type={tjr.request_type}")
else:
    print("✗ No registration found in database")

print(f"\n{'='*70}\n")
