from django.db import transaction
from accounts.models import User, PlayerProfile
from tournaments.models import Tournament, TournamentRegistration, Group, Match, MatchScore

# Cleanup any auto-created COD registrations and lobby data
AUTO_PREFIX = "AutoTeam_COD_"

# Find tournaments that have AUTO_PREFIX registrations
auto_regs = TournamentRegistration.objects.filter(team_name__startswith=AUTO_PREFIX)
affected_tournament_ids = set(reg.tournament.id for reg in auto_regs)

print(f"Found auto registrations for tournaments: {affected_tournament_ids}")

for tid in affected_tournament_ids:
    try:
        t = Tournament.objects.get(id=tid)
    except Tournament.DoesNotExist:
        continue
    print(f"Cleaning tournament {t.id} - {t.title}")

    # Delete groups named as Lobbies for this tournament
    lobbies = Group.objects.filter(tournament=t, group_name__istartswith='Lobby')
    lobby_ids = [g.id for g in lobbies]
    print(f"  Deleting {len(lobbies)} lobby groups")

    # Delete matches and match scores for these lobbies
    matches = Match.objects.filter(group__in=lobbies)
    ms_count = MatchScore.objects.filter(match__in=matches).count()
    print(f"  Deleting {ms_count} match scores and {matches.count()} matches")
    MatchScore.objects.filter(match__in=matches).delete()
    matches.delete()

    # Delete the lobby groups
    lobbies.delete()

    # Remove auto registrations for this tournament
    regs = TournamentRegistration.objects.filter(tournament=t, team_name__startswith=AUTO_PREFIX)
    print(f"  Deleting {regs.count()} auto registrations")
    regs.delete()

    # Reset tournament fields that were modified by the simulation
    t.selected_teams = {}
    t.round_status = {}
    t.winners = {}
    t.current_round = 0
    # Recalculate current_participants (after deletion)
    t.current_participants = t.registrations.count()
    t.save(update_fields=['selected_teams','round_status','winners','current_round','current_participants'])
    print(f"  Tournament {t.id} cleaned. current_participants={t.current_participants}")

# Now add registrations to tournament 22 only
TARGET_TID = 22
try:
    target = Tournament.objects.get(id=TARGET_TID)
except Tournament.DoesNotExist:
    print(f"Tournament {TARGET_TID} not found. Exiting.")
    raise SystemExit(1)

DESIRED = 8
created = []

# Create or reuse player profiles
existing_players = list(PlayerProfile.objects.all())[:DESIRED]

# create users if needed
if len(existing_players) < DESIRED:
    for i in range(len(existing_players)+1, DESIRED+1):
        username = f"cod22_p{i}"
        email = f"{username}@example.com"
        user = User.objects.create_user(username=username, email=email, password='password', user_type='player', phone_number='9999999999')
        pp = PlayerProfile.objects.create(user=user)
        existing_players.append(pp)

for idx, pp in enumerate(existing_players, start=1):
    tr, created_flag = TournamentRegistration.objects.get_or_create(
        tournament=target,
        player=pp,
        defaults={
            'team_name': f"AutoTeam_COD_{idx}",
            'team_members': [pp.user.username],
            'status': 'confirmed',
            'payment_status': True,
        }
    )
    created.append((tr, created_flag))

# Update tournament current_participants
target.current_participants = target.registrations.count()
target.save(update_fields=['current_participants'])

print(f"Added/ensured {len(created)} registrations for tournament {target.id}. current_participants={target.current_participants}")
for tr, flag in created:
    print(f" RegID: {tr.id} | Team: {tr.team_name} | Player: {tr.player.user.username} | New: {flag}")
