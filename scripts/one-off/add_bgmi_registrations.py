from accounts.models import User, PlayerProfile
from tournaments.models import Tournament, TournamentRegistration

# Add registrations to both BGMI tournaments
TOURNAMENT_IDS = [19, 20]  # Squad and Duo
REGISTRATIONS_PER_TOURNAMENT = 16

for tid in TOURNAMENT_IDS:
    try:
        tournament = Tournament.objects.get(id=tid)
    except Tournament.DoesNotExist:
        print(f"Tournament {tid} not found. Skipping.")
        continue
    
    print(f"\nAdding registrations to Tournament {tid} - {tournament.title} ({tournament.game_name})")
    
    # Get or create 16 player profiles
    existing_players = list(PlayerProfile.objects.all()[:REGISTRATIONS_PER_TOURNAMENT])
    
    # Create missing players if needed
    if len(existing_players) < REGISTRATIONS_PER_TOURNAMENT:
        for i in range(len(existing_players) + 1, REGISTRATIONS_PER_TOURNAMENT + 1):
            username = f"bgmi_t{tid}_p{i}"
            email = f"{username}@example.com"
            user = User.objects.create_user(
                username=username,
                email=email,
                password='password',
                user_type='player',
                phone_number='9999999999'
            )
            pp = PlayerProfile.objects.create(user=user)
            existing_players.append(pp)
    
    # Create registrations
    created_count = 0
    for idx, pp in enumerate(existing_players[:REGISTRATIONS_PER_TOURNAMENT], start=1):
        tr, created_flag = TournamentRegistration.objects.get_or_create(
            tournament=tournament,
            player=pp,
            defaults={
                'team_name': f"Team_{tid}_{idx}",
                'team_members': [pp.user.username],
                'status': 'confirmed',
                'payment_status': True,
            }
        )
        if created_flag:
            created_count += 1
    
    # Update current_participants
    tournament.current_participants = tournament.registrations.count()
    tournament.save(update_fields=['current_participants'])
    
    print(f"  Created {created_count} new registrations. Total: {tournament.current_participants}")
    
    # List registered teams
    for reg in tournament.registrations.all()[:5]:
        print(f"    - {reg.team_name} ({reg.player.user.username})")
    if tournament.registrations.count() > 5:
        print(f"    ... and {tournament.registrations.count() - 5} more")

print("\nDone! Both BGMI tournaments now have registrations.")
