"""
Management command: seed_ui_test_tournaments
Creates 4 tournaments for UI testing (BGMI, Valorant, COD Mobile, Scrim)
each with multi-round config and registered teams.

Usage:
    python manage.py seed_ui_test_tournaments
    python manage.py seed_ui_test_tournaments --host kishan@qodet.com
    python manage.py seed_ui_test_tournaments --flush   (delete existing test data first)
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, date
from accounts.models import User, HostProfile, PlayerProfile, Team, TeamMember
from tournaments.models import Tournament, TournamentRegistration


TEAM_NAMES = [
    'Phoenix Squad', 'Dragon Force', 'Tiger Team', 'Viper Squad', 'Shadow Clan',
    'Ghost Protocol', 'Alpha Team', 'Beta Squad', 'Cyber Warriors', 'Elite Force',
    'Thunder Strike', 'Inferno Team', 'Mystique Force', 'Nova Squad', 'Titan Force',
    'Warrior Kings', 'Stellar Squad', 'Victory Team', 'Champion Force', 'Apex Hunters',
    'Blaze Unit', 'Storm Riders', 'Iron Wolves', 'Night Owls', 'Reaper Squad',
]


class Command(BaseCommand):
    help = 'Seed 4 UI test tournaments (BGMI, Valorant, COD Mobile, Scrim) with teams'

    def add_arguments(self, parser):
        parser.add_argument('--host', type=str, default='kishan@qodet.com',
                            help='Host email to assign tournaments to')
        parser.add_argument('--flush', action='store_true',
                            help='Delete existing seed tournaments before creating')

    def handle(self, *args, **options):
        host_email = options['host']
        flush = options['flush']

        # --- Get host ---
        try:
            host_user = User.objects.get(email=host_email)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Host {host_email} not found!'))
            return
        try:
            host_profile = host_user.host_profile
        except Exception:
            self.stdout.write(self.style.ERROR('Host profile not found!'))
            return

        now = timezone.now()

        # --- Tournament definitions ---
        tournament_defs = [
            {
                'title': '[TEST] BGMI Grand Championship S1',
                'game_name': 'BGMI',
                'game_mode': 'Squad',
                'status': 'ongoing',
                'entry_fee': 100,
                'prize_pool': 50000,
                'max_participants': 20,
                'team_count': 20,
                'rounds': [
                    {'round': 1, 'max_teams': 20, 'qualifying_teams': 12},
                    {'round': 2, 'max_teams': 12, 'qualifying_teams': 6},
                    {'round': 3, 'max_teams': 6,  'qualifying_teams': 1},
                ],
                'round_names': {'1': 'Qualifiers', '2': 'Semi Finals', '3': 'Grand Finals'},
                'current_round': 1,
                'round_status': {'1': 'ongoing', '2': 'upcoming', '3': 'upcoming'},
                'placement_points': {'1': 15, '2': 12, '3': 10, '4': 8, '5': 6,
                                     '6': 4, '7': 3, '8': 2, '9': 1, '10': 1},
                'is_featured': True,
            },
            {
                'title': '[TEST] Valorant Open Cup 2026',
                'game_name': 'Valorant',
                'game_mode': '5v5',
                'status': 'ongoing',
                'entry_fee': 150,
                'prize_pool': 75000,
                'max_participants': 16,
                'team_count': 16,
                'rounds': [
                    {'round': 1, 'max_teams': 16, 'qualifying_teams': 8},
                    {'round': 2, 'max_teams': 8,  'qualifying_teams': 4},
                    {'round': 3, 'max_teams': 4,  'qualifying_teams': 1},
                ],
                'round_names': {'1': 'Group Stage', '2': 'Quarter Finals', '3': 'Finals'},
                'current_round': 2,
                'round_status': {'1': 'completed', '2': 'ongoing', '3': 'upcoming'},
                'placement_points': {'1': 10, '2': 7, '3': 5, '4': 3},
                'is_featured': True,
            },
            {
                'title': '[TEST] COD Mobile Warzone Clash',
                'game_name': 'COD',
                'game_mode': 'Squad',
                'status': 'upcoming',
                'entry_fee': 50,
                'prize_pool': 20000,
                'max_participants': 25,
                'team_count': 15,
                'rounds': [
                    {'round': 1, 'max_teams': 25, 'qualifying_teams': 10},
                    {'round': 2, 'max_teams': 10, 'qualifying_teams': 1},
                ],
                'round_names': {'1': 'Qualifiers', '2': 'Grand Finals'},
                'current_round': 0,
                'round_status': {'1': 'upcoming', '2': 'upcoming'},
                'placement_points': {'1': 12, '2': 9, '3': 7, '4': 5, '5': 3,
                                     '6': 2, '7': 1},
                'is_featured': False,
            },
            {
                'title': '[TEST] BGMI Weekly Scrim #12',
                'game_name': 'BGMI',
                'game_mode': 'Squad',
                'status': 'ongoing',
                'entry_fee': 0,
                'prize_pool': 0,
                'max_participants': 12,
                'team_count': 12,
                'rounds': [
                    {'round': 1, 'max_teams': 12, 'qualifying_teams': 12},
                ],
                'round_names': {'1': 'Match Day'},
                'current_round': 1,
                'round_status': {'1': 'ongoing'},
                'placement_points': {'1': 10, '2': 6, '3': 4, '4': 3, '5': 2, '6': 1},
                'is_featured': False,
                'event_mode': 'SCRIM',
                'max_matches': 4,
            },
        ]

        # --- Flush if requested ---
        if flush:
            for tdef in tournament_defs:
                deleted, _ = Tournament.objects.filter(
                    title=tdef['title'], host=host_profile
                ).delete()
                if deleted:
                    self.stdout.write(self.style.WARNING(f"Deleted: {tdef['title']}"))

        # --- Ensure shared test players exist (25 teams × 5 members) ---
        self.stdout.write('\nEnsuring test player accounts exist...')
        player_profiles = self._ensure_players()

        # --- Create each tournament ---
        for tdef in tournament_defs:
            self._create_tournament(host_profile, tdef, player_profiles, now)

        self.stdout.write(self.style.SUCCESS('\nSeed complete! All 4 tournaments created.'))
        self.stdout.write('Log in as host and visit the dashboard to test.')

    # -------------------------------------------------------------------------
    def _ensure_players(self):
        """Create/retrieve 25 player accounts (5 per team × 25 names)."""
        profiles = []
        for idx in range(1, 26):
            email = f'uitest_player{idx}@scrimverse.test'
            try:
                u = User.objects.get(email=email)
            except User.DoesNotExist:
                u = User.objects.create_user(
                    email=email,
                    username=f'uitest_p{idx}',
                    password='Test@1234',
                    user_type='player',
                    phone_number=f'90000{idx:05d}',
                )
                u.is_email_verified = True
                u.save()
            profile, _ = PlayerProfile.objects.get_or_create(user=u)
            profiles.append(profile)
        self.stdout.write(f'  {len(profiles)} player profiles ready.')
        return profiles

    def _get_or_create_team(self, slot, captain_profile, members_start):
        """Return (team, captain_profile) — create if needed."""
        team_name = TEAM_NAMES[slot]
        team = Team.objects.filter(name=team_name).first()
        if team:
            return team, captain_profile

        captain_user = captain_profile.user
        team = Team.objects.create(
            name=team_name,
            description=f'{team_name} — UI test team',
            captain=captain_user,
            is_temporary=False,
        )
        # Captain member entry
        TeamMember.objects.get_or_create(
            team=team, user=captain_user,
            defaults={'username': captain_user.username, 'is_captain': True}
        )
        return team, captain_profile

    def _create_tournament(self, host_profile, tdef, player_profiles, now):
        title = tdef['title']
        existing = Tournament.objects.filter(title=title, host=host_profile).first()
        if existing:
            self.stdout.write(self.style.WARNING(f'Already exists, skipping: {title}'))
            return

        is_scrim = tdef.get('event_mode') == 'SCRIM'

        # Build times relative to now
        reg_start = now - timedelta(days=3)
        reg_end = now + timedelta(days=1)
        t_start = now - timedelta(days=1)
        t_end = now + timedelta(days=7)

        if tdef['status'] == 'upcoming':
            reg_start = now + timedelta(hours=1)
            reg_end = now + timedelta(days=5)
            t_start = now + timedelta(days=7)
            t_end = now + timedelta(days=8)

        create_kwargs = dict(
            host=host_profile,
            title=title,
            description=f'UI test tournament — {tdef["game_name"]}. {len(tdef["rounds"])} rounds.',
            game_name=tdef['game_name'],
            game_mode=tdef['game_mode'],
            event_mode=tdef.get('event_mode', 'TOURNAMENT'),
            max_participants=tdef['max_participants'],
            current_participants=0,
            entry_fee=tdef['entry_fee'],
            prize_pool=tdef['prize_pool'],
            tournament_date=t_start.date(),
            tournament_time=t_start.time(),
            registration_start=reg_start,
            registration_end=reg_end,
            tournament_start=t_start,
            tournament_end=t_end,
            rules='Standard rules apply. No teaming. No hacking. Host decisions are final.',
            requirements=['Minimum account level 30', 'No emulator'],
            status=tdef['status'],
            rounds=tdef['rounds'],
            round_names=tdef['round_names'],
            current_round=tdef['current_round'],
            round_status=tdef['round_status'],
            placement_points=tdef['placement_points'],
            is_featured=tdef['is_featured'],
            plan_payment_status=True,
            plan_payment_id='UITEST_PLAN',
        )
        if is_scrim:
            create_kwargs['max_matches'] = tdef.get('max_matches', 4)

        tournament = Tournament.objects.create(**create_kwargs)
        self.stdout.write(f'\nCreated: {title} (ID: {tournament.id})')

        # --- Register teams ---
        team_count = tdef['team_count']
        registered = 0
        for slot in range(team_count):
            captain_profile = player_profiles[slot % len(player_profiles)]
            team, captain_profile = self._get_or_create_team(slot, captain_profile, slot)

            # Skip if this player already registered in this tournament
            if TournamentRegistration.objects.filter(
                tournament=tournament, player=captain_profile
            ).exists():
                continue

            TournamentRegistration.objects.create(
                tournament=tournament,
                player=captain_profile,
                team=team,
                team_name=team.name,
                status='confirmed',
                payment_status=True,
                is_team_created=True,
            )
            registered += 1

        # Update participant count
        tournament.current_participants = TournamentRegistration.objects.filter(
            tournament=tournament, status='confirmed'
        ).count()
        tournament.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'  OK {registered} teams registered | '
                f'status={tournament.status} | rounds={len(tdef["rounds"])} | '
                f'current_round={tdef["current_round"]}'
            )
        )
