#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, TeamMember, Team, TeamJoinRequest, PlayerProfile
from tournaments.models import Tournament, TournamentRegistration

# Find the specific user
try:
    u = User.objects.get(email='kishanbm2300@gmail.com')
    print(f"✅ Found user: {u.email} (ID: {u.id})")
    
    # Try to get their player profile
    try:
        pp = u.player_profile
        print(f"✅ Player Profile exists (ID: {pp.id})")
    except:
        print("❌ No player profile found")
        print("\nCreating player profile...")
        from accounts.models import PlayerProfile
        pp = PlayerProfile.objects.create(user=u, username=u.email.split('@')[0])
        print(f"✅ Created player profile (ID: {pp.id})")
    
except User.DoesNotExist:
    print(f"❌ User not found: kishanbm2300@gmail.com")
    print("\nShowing all users with '2300' in email:")
    users = User.objects.filter(email__contains='2300')
    for user in users:
        print(f"  - {user.email} (ID: {user.id})")
    if not users.exists():
        print("  None found")
    exit(1)

# Check team memberships
team_memberships = TeamMember.objects.filter(user=u)
print(f"\n✅ Team memberships: {team_memberships.count()}")
for tm in team_memberships:
    print(f"  - Team: {tm.team.name} (ID: {tm.team.id})")

# Check registrations for this user
regs = TournamentRegistration.objects.filter(player__user=u)
print(f"\n📋 Registrations for this user: {regs.count()}")
for reg in regs:
    print(f"  - {reg.tournament.title} (Team ID: {reg.team_id})")

# Get a free tournament to test with
print("\n" + "="*60)
print("AVAILABLE FREE TOURNAMENTS TO TEST:")
print("="*60)
free_tournaments = Tournament.objects.filter(entry_fee=0)[:5]
for t in free_tournaments:
    print(f"  {t.id}: {t.title} (Fee: {t.entry_fee})")

if not free_tournaments.exists():
    print("  No free tournaments available!")
else:
    # Create a test registration with a free tournament
    tournament = free_tournaments.first()
    print(f"\n📝 Creating test registration...")
    print(f"   Tournament: {tournament.title} (ID: {tournament.id})")
    print(f"   Player: {u.email}")
    
    # Create team
    team = Team.objects.create(
        name=f"Test Team {u.id}",
        captain=u,
        is_temporary=True
    )
    print(f"   Created team: {team.name} (ID: {team.id})")
    
    # Create registration with team
    reg = TournamentRegistration.objects.create(
        tournament=tournament,
        player=pp,
        team=team,
        team_name=team.name,
        status='pending',
        payment_status=False,
    )
    print(f"   Created registration: (ID: {reg.id})")
    print(f"   Registration.team: {reg.team.name} (ID: {reg.team_id})")
    
    # Now test the my-registrations query
    print(f"\n✅ VERIFICATION:")
    regs_direct = TournamentRegistration.objects.filter(player=pp)
    print(f"   Direct registrations (player match): {regs_direct.count()}")
    
    user_team_ids = [tm.team_id for tm in TeamMember.objects.filter(user=u)]
    print(f"   User's team IDs: {user_team_ids}")
    
    if user_team_ids:
        regs_via_team = TournamentRegistration.objects.filter(team_id__in=user_team_ids)
        print(f"   Via team membership: {regs_via_team.count()}")
    
    total = regs_direct.count() + (len(regs_via_team) if user_team_ids else 0)
    print(f"\n{'✅ SUCCESS' if total > 0 else '❌ FAILED'}: Total visible: {total}")
