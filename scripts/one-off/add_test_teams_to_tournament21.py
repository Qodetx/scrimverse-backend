"""Create multiple temporary teams and registrations for a tournament (id 21).

Script actions:
- Select PlayerProfiles not already registered for tournament 21
- Create Team entries (is_temporary=True) with a captain
- Add TeamMember rows for 5 members per team
- Create TournamentRegistration linked to team and set status confirmed

Run with: python manage.py shell -c "exec(open('scripts/add_test_teams_to_tournament21.py').read())"
"""

from django.db import transaction

NUM_TEAMS = 16
MEMBERS_PER_TEAM = 5
TOURNAMENT_ID = 21

from accounts.models import Team, TeamMember, PlayerProfile, User
from tournaments.models import Tournament, TournamentRegistration

print(f"Starting team creation for tournament {TOURNAMENT_ID}")

try:
    tournament = Tournament.objects.get(id=TOURNAMENT_ID)
except Tournament.DoesNotExist:
    print('Tournament not found:', TOURNAMENT_ID)
    raise SystemExit(1)

# players already registered (user ids)
registered_user_ids = list(
    TournamentRegistration.objects.filter(tournament=tournament).values_list('player__user__id', flat=True)
)

# available player profiles not already registered
available_profiles = list(
    PlayerProfile.objects.exclude(user__id__in=registered_user_ids).order_by('id')
)

needed_players = NUM_TEAMS * MEMBERS_PER_TEAM
if len(available_profiles) < needed_players:
    print(f"Warning: only {len(available_profiles)} available player profiles, need {needed_players}. Will create {len(available_profiles)//MEMBERS_PER_TEAM} teams instead.")
    NUM_TEAMS = len(available_profiles) // MEMBERS_PER_TEAM

created = []
idx = 0
with transaction.atomic():
    for tnum in range(NUM_TEAMS):
        # Pick captain
        captain_profile = available_profiles[idx]
        idx += 1
        # Create team
        team_name = f"AutoTeam_{TOURNAMENT_ID}_{tnum+1}"
        team = Team.objects.create(name=team_name, captain=captain_profile.user, is_temporary=True)

        members = []
        # Add captain as TeamMember
        TeamMember.objects.create(team=team, user=captain_profile.user, username=captain_profile.user.username, is_captain=True)
        members.append({'id': captain_profile.id, 'username': captain_profile.user.username})

        # Add additional members
        for m in range(MEMBERS_PER_TEAM - 1):
            if idx >= len(available_profiles):
                break
            p = available_profiles[idx]
            idx += 1
            TeamMember.objects.create(team=team, user=p.user, username=p.user.username, is_captain=False)
            members.append({'id': p.id, 'username': p.user.username})

        # Create TournamentRegistration for captain (player field expects PlayerProfile)
        reg = TournamentRegistration.objects.create(
            tournament=tournament,
            player=captain_profile,
            team=team,
            team_name=team_name,
            team_members=members,
            status='confirmed',
            payment_status=True,
            is_team_created=True,
        )

        created.append((team.id, reg.id, team_name, len(members)))

print('Created teams and registrations:')
for t in created:
    print(f"  Team id={t[0]} reg_id={t[1]} name={t[2]} members={t[3]}")

print('Done')
