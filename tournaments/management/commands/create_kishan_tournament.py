from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import User, HostProfile, PlayerProfile, Team, TeamMember
from tournaments.models import Tournament, TournamentRegistration


class Command(BaseCommand):
    help = 'Create tournament for kishan@qodet.com host with 20 BGMI teams'

    def handle(self, *args, **options):
        self.stdout.write("Creating tournament for kishan@qodet.com...")
        
        # Get the host user
        try:
            host_user = User.objects.get(email='kishan@qodet.com')
            self.stdout.write(self.style.SUCCESS(f"Found host: {host_user.email}"))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR("Host kishan@qodet.com not found!"))
            return
        
        try:
            host_profile = host_user.host_profile
        except:
            self.stdout.write(self.style.ERROR("Host profile not found!"))
            return
        
        # Create tournament for this host
        tournament_title = 'BGMI Test Tournament - 20 Teams'
        tournament = Tournament.objects.filter(title=tournament_title, host=host_profile).first()
        
        if not tournament:
            now = timezone.now()
            tournament = Tournament.objects.create(
                host=host_profile,
                title=tournament_title,
                description='Test tournament for CSV export testing',
                game_name='BGMI',
                game_mode='Squad',
                max_participants=20,
                current_participants=0,
                entry_fee=100,
                prize_pool=10000,
                tournament_date=now.date() + timedelta(days=7),
                tournament_time=now.time(),
                registration_start=now,
                registration_end=now + timedelta(hours=2),
                tournament_start=now + timedelta(days=7),
                tournament_end=now + timedelta(days=8),
                rules='Test tournament rules',
                status='upcoming',
                plan_payment_status=True,
                plan_payment_id='TEST_PLAN'
            )
            self.stdout.write(self.style.SUCCESS(f"Created tournament: {tournament.title} (ID: {tournament.id})"))
        else:
            self.stdout.write(self.style.WARNING(f"Tournament already exists: {tournament.title} (ID: {tournament.id})"))
            # Delete existing registrations to start fresh
            TournamentRegistration.objects.filter(tournament=tournament).delete()
            self.stdout.write("Cleared existing registrations")
        
        # Create 20 teams with members
        team_names = [
            'Phoenix Squad', 'Dragon Force', 'Tiger Team', 'Viper Squad', 'Shadow Clan',
            'Ghost Protocol', 'Alpha Team', 'Beta Squad', 'Cyber Warriors', 'Elite Force',
            'Thunder Strike', 'Inferno Team', 'Mystique Force', 'Apex Legends', 'Nova Squad',
            'Titan Force', 'Warrior Kings', 'Stellar Squad', 'Victory Team', 'Champion Force'
        ]
        
        created_count = 0
        for idx, team_name in enumerate(team_names, 1):
            # Check if team exists
            team = Team.objects.filter(name=team_name).first()
            
            if not team:
                # Create team captain
                captain_email = f'kishan_captain{idx}@test.com'
                try:
                    captain_user = User.objects.get(email=captain_email)
                except User.DoesNotExist:
                    captain_user = User.objects.create_user(
                        email=captain_email,
                        username=f'kishan_captain{idx}',
                        password='testpass123',
                        user_type='player',
                        phone_number=f'98500{idx:05d}'
                    )
                    captain_user.is_email_verified = True
                    captain_user.save()
                    
                    # Create player profile
                    PlayerProfile.objects.get_or_create(user=captain_user)
                
                # Create team
                team = Team.objects.create(
                    name=team_name,
                    description=f'{team_name} - Test Team',
                    captain=captain_user,
                    is_temporary=False
                )
                
                # Create team members (4 additional members per team)
                for member_idx in range(1, 5):
                    # Use unique emails for each member
                    member_email = f'kishan_member{idx}_{member_idx}@test.com'
                    try:
                        member_user = User.objects.get(email=member_email)
                    except User.DoesNotExist:
                        member_user = User.objects.create_user(
                            email=member_email,
                            username=f'kishan_member{idx}_{member_idx}',
                            password='testpass123',
                            user_type='player',
                            phone_number=f'97{idx:03d}{member_idx:04d}'
                        )
                        member_user.is_email_verified = True
                        member_user.save()
                        
                        # Create player profile
                        PlayerProfile.objects.get_or_create(user=member_user)
                    
                    # Add to team
                    TeamMember.objects.get_or_create(
                        team=team,
                        user=member_user,
                        username=member_user.username,
                        is_captain=False
                    )
                
                # Add captain as team member
                TeamMember.objects.get_or_create(
                    team=team,
                    user=captain_user,
                    username=captain_user.username,
                    is_captain=True
                )
                
                # Create tournament registration
                try:
                    captain_player_profile = captain_user.player_profile
                except:
                    captain_player_profile = PlayerProfile.objects.create(user=captain_user)
                
                TournamentRegistration.objects.create(
                    tournament=tournament,
                    player=captain_player_profile,
                    team=team,
                    team_name=team_name,
                    status='confirmed',
                    payment_status=True,
                    is_team_created=True
                )
                
                created_count += 1
                self.stdout.write(f"Created team {created_count}: {team_name} with 5 members (1 captain + 4 members)")
            else:
                # Check if registration exists
                try:
                    captain_player_profile = team.captain.player_profile
                except:
                    captain_player_profile = PlayerProfile.objects.create(user=team.captain)
                
                registration = TournamentRegistration.objects.filter(
                    tournament=tournament,
                    team=team
                ).first()
                
                if not registration:
                    TournamentRegistration.objects.create(
                        tournament=tournament,
                        player=captain_player_profile,
                        team=team,
                        team_name=team.name,
                        status='confirmed',
                        payment_status=True,
                        is_team_created=True
                    )
                    created_count += 1
                    self.stdout.write(f"Added existing team to tournament: {team_name}")
        
        # Update tournament participant count
        tournament.current_participants = TournamentRegistration.objects.filter(
            tournament=tournament,
            status='confirmed'
        ).values('team').distinct().count()
        tournament.save()
        
        self.stdout.write(self.style.SUCCESS(f"\n✓ Test data generation complete!"))
        self.stdout.write(f"Host: {host_user.email}")
        self.stdout.write(f"Tournament: {tournament.title}")
        self.stdout.write(f"Tournament ID: {tournament.id}")
        self.stdout.write(f"Total teams registered: {tournament.current_participants}")
        
        # Count members
        total_members = TournamentRegistration.objects.filter(tournament=tournament).count()
        for reg in TournamentRegistration.objects.filter(tournament=tournament):
            if reg.team:
                total_members += reg.team.members.count()
        
        self.stdout.write(f"Total members in all teams: {total_members}")
        self.stdout.write(f"\nTest CSV export at: /api/tournaments/{tournament.id}/registrations/export/")
