#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration
from accounts.models import HostProfile

print("\n" + "="*80)
print("🔧 UPDATING TOURNAMENT STATISTICS")
print("="*80)

# Update Tournament 75
try:
    t75 = Tournament.objects.get(id=75)
    
    # Count player registrations (exclude team-only registrations)
    player_count = TournamentRegistration.objects.filter(
        tournament=t75,
        player__isnull=False
    ).count()
    
    # Get unique teams
    team_count = TournamentRegistration.objects.filter(
        tournament=t75,
        player__isnull=False
    ).values('team').distinct().count()
    
    # Update tournament
    old_participants = t75.current_participants
    t75.current_participants = player_count
    t75.save(update_fields=['current_participants'])
    
    print(f"✅ Tournament 75 (BGMI Squad 4v4 Test Tournament 2)")
    print(f"   - Players: {old_participants} → {player_count}")
    print(f"   - Teams: {team_count}")
    
except Tournament.DoesNotExist:
    print("❌ Tournament 75 not found")

# Update all tournaments stats
print("\n" + "="*52)
print("📊 UPDATING ALL TOURNAMENTS")
print("="*52)

total_participants = 0
for tournament in Tournament.objects.filter(status__in=['ongoing', 'upcoming', 'completed']):
    player_count = TournamentRegistration.objects.filter(
        tournament=tournament,
        player__isnull=False
    ).count()
    
    if player_count > 0:
        tournament.current_participants = player_count
        tournament.save(update_fields=['current_participants'])
        total_participants += player_count
        print(f"✅ {tournament.title}: {player_count} players")

# Update Host Profile statistics
print("\n" + "="*52)
print("👨‍💼 UPDATING HOST PROFILE STATISTICS")
print("="*52)

try:
    host = HostProfile.objects.get(user__email='kishan@qodet.com')
    
    # Count total tournaments hosted
    total_tournaments = Tournament.objects.filter(host=host).count()
    old_count = host.total_tournaments_hosted
    host.total_tournaments_hosted = total_tournaments
    host.save(update_fields=['total_tournaments_hosted'])
    
    print(f"✅ Host: kishan@qodet.com")
    print(f"   - Tournaments hosted: {old_count} → {total_tournaments}")
    print(f"   - Total participants across all tournaments: {total_participants}")
    
except HostProfile.DoesNotExist:
    print("❌ Host profile not found")

print("\n" + "="*80)
print("✅ STATISTICS UPDATE COMPLETE!")
print("="*80)
