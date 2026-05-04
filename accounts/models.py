import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from accounts.validators import validate_aadhar_image


class User(AbstractUser):
    """
    Custom User model with role-based authentication
    """

    USER_TYPE_CHOICES = (
        ("player", "Player"),
        ("host", "Host"),
        ("admin", "Admin"),
    )

    email = models.EmailField(unique=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)
    phone_number = models.CharField(max_length=15, blank=True, default='')
    profile_picture = models.ImageField(upload_to="profiles/", blank=True, null=True)
    username_change_count = models.IntegerField(default=0)
    last_username_change = models.DateTimeField(null=True, blank=True)

    # Email Verification
    is_email_verified = models.BooleanField(default=False, help_text="Whether email is verified")
    email_verification_token = models.CharField(
        max_length=100, blank=True, null=True, help_text="Token for email verification"
    )
    email_verification_sent_at = models.DateTimeField(
        null=True, blank=True, help_text="When verification email was sent"
    )
    post_verify_redirect = models.CharField(
        max_length=500, blank=True, null=True, help_text="URL to redirect to after email verification"
    )

    # Phone Verification
    is_phone_verified = models.BooleanField(default=False, help_text="Whether phone number is verified via OTP")

    # Password Reset
    password_reset_token = models.CharField(max_length=100, blank=True, null=True, help_text="Token for password reset")
    password_reset_sent_at = models.DateTimeField(null=True, blank=True, help_text="When password reset email was sent")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "user_type"]

    def __str__(self):
        return f"{self.email} - {self.user_type}"

    class Meta:
        db_table = "users"


class PlayerProfile(models.Model):
    """
    Extended profile for players
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="player_profile")
    in_game_name = models.CharField(max_length=100, blank=True, default="", help_text="Player's in-game name")
    game_id = models.CharField(max_length=100, blank=True, default="", help_text="Player's game ID or UID")
    preferred_games = models.JSONField(default=list, blank=True)  # List of games
    notification_preferences = models.JSONField(
        default=dict,
        blank=True,
        help_text="Player notification preferences: {enableNotifications, matchReminders, tournamentUpdates, teamInvites, marketingEmails}"
    )
    game_profiles = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Per-game IGN and Game ID. '
            'Format: {"BGMI": {"ign": "...", "game_id": "..."}, "Valorant": {...}, ...}. '
            'Supported keys: BGMI, Valorant, COD, Freefire, Scarfall.'
        ),
    )
    bio = models.TextField(blank=True)
    total_tournaments_participated = models.IntegerField(default=0)
    total_wins = models.IntegerField(default=0)

    def __str__(self):
        return f"Player: {self.user.username}"

    class Meta:
        db_table = "player_profiles"


class HostProfile(models.Model):
    """
    Extended profile for hosts/organizers
    """

    VERIFICATION_STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="host_profile")
    bio = models.TextField(blank=True)
    website = models.URLField(blank=True)
    social_links = models.JSONField(
        default=dict,
        blank=True,
        help_text='Social links: {"instagram": "...", "youtube": "...", "discord": "..."}',
    )
    notification_preferences = models.JSONField(
        default=dict,
        blank=True,
        help_text="Host notification preferences: {newRegistrations, matchAlerts, paymentAlerts, systemUpdates}",
    )
    payout_details = models.JSONField(
        default=dict,
        blank=True,
        help_text='Payout details (private): {"method": "bank"|"upi", "bank_name": "...", "account_number": "...", "ifsc_code": "...", "upi_id": "..."}',
    )
    total_tournaments_hosted = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)  # Out of 5
    total_ratings = models.IntegerField(default=0)
    verified = models.BooleanField(default=False)

    # Aadhar Card Verification Fields
    aadhar_card_front = models.ImageField(
        upload_to="aadhar_cards/",
        blank=True,
        null=True,
        validators=[validate_aadhar_image],
        help_text="Front side of Aadhar card (max 5MB, formats: JPG, JPEG, PNG, WEBP)",
    )
    aadhar_card_back = models.ImageField(
        upload_to="aadhar_cards/",
        blank=True,
        null=True,
        validators=[validate_aadhar_image],
        help_text="Back side of Aadhar card (max 5MB, formats: JPG, JPEG, PNG, WEBP)",
    )
    aadhar_uploaded_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when Aadhar was uploaded")
    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_STATUS_CHOICES, default="pending", help_text="Verification status"
    )
    verification_notes = models.TextField(blank=True, help_text="Admin notes for verification (e.g., rejection reason)")

    def __str__(self):
        return f"Host: {self.user.username}"

    class Meta:
        db_table = "host_profiles"


class Team(models.Model):
    """
    Team model for players to group up
    """

    GAME_CHOICES = [
        ('BGMI', 'BGMI'),
        ('Valorant', 'Valorant'),
        ('Free Fire', 'Free Fire'),
        ('COD Mobile', 'COD Mobile'),
        ('Scarfall', 'Scarfall'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="WE ARE BEAST", help_text="Team tagline or description")
    profile_picture = models.ImageField(
        upload_to="teams/", blank=True, null=True, help_text="Team logo/profile picture"
    )
    captain = models.ForeignKey(User, on_delete=models.CASCADE, related_name="managed_teams")
    created_at = models.DateTimeField(auto_now_add=True)
    is_temporary = models.BooleanField(default=False, help_text="True if created for a single tournament")
    game = models.CharField(max_length=50, null=True, blank=True, choices=GAME_CHOICES, help_text="Primary game for this team")
    linked_tournament = models.ForeignKey(
        'tournaments.Tournament',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='temp_teams',
        help_text="Tournament this temp team was created for"
    )
    conversion_deadline = models.DateTimeField(
        null=True, blank=True,
        help_text="48h window for captain to keep this temp team permanently"
    )

    # Statistics (dummy data for now)
    total_matches = models.IntegerField(default=0)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)

    @property
    def win_rate(self):
        if self.total_matches == 0:
            return 0
        return round((self.wins / self.total_matches) * 100)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "teams"


class TeamStatistics(models.Model):
    """
    Leaderboard statistics for teams
    Tracks tournament and scrim wins and cumulative points separately
    Now supports game-specific stats tracking (BGMI, COD, Valorant, etc.)
    """

    GAME_CHOICES = [
        ('BGMI', 'BGMI'),
        ('COD', 'Call of Duty'),
        ('Valorant', 'Valorant'),
        ('Freefire', 'Free Fire'),
        ('Scarfall', 'Scarfall'),
        ('ALL', 'All Games'),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="statistics_by_game")
    game_name = models.CharField(
        max_length=100,
        choices=GAME_CHOICES,
        default='ALL',
        help_text="Game-specific stats. 'ALL' represents aggregate stats across all games."
    )

    # Tournament Statistics
    tournament_wins = models.IntegerField(default=0, help_text="Number of tournament victories (1st place finishes)")
    tournament_position_points = models.IntegerField(default=0, help_text="Position points from tournaments only")
    tournament_kill_points = models.IntegerField(default=0, help_text="Kill points from tournaments only")

    # Scrim Statistics
    scrim_wins = models.IntegerField(default=0, help_text="Number of scrim victories (1st place finishes)")
    scrim_position_points = models.IntegerField(default=0, help_text="Position points from scrims only")
    scrim_kill_points = models.IntegerField(default=0, help_text="Kill points from scrims only")

    # Combined Statistics (for backward compatibility)
    total_position_points = models.IntegerField(default=0, help_text="Cumulative position points from all matches")
    total_kill_points = models.IntegerField(default=0, help_text="Cumulative kill points from all matches")
    total_points = models.IntegerField(default=0, help_text="Total points (position + kill)")
    rank = models.IntegerField(default=0, help_text="Total (overall) leaderboard rank")
    tournament_rank = models.IntegerField(default=0, help_text="Tournament leaderboard rank")
    scrim_rank = models.IntegerField(default=0, help_text="Scrim leaderboard rank")

    # Match counts
    tournament_matches_played = models.IntegerField(default=0, help_text="Number of individual tournament matches played")
    scrim_matches_played = models.IntegerField(default=0, help_text="Number of individual scrim matches played")
    matches_played = models.IntegerField(default=0, help_text="Total individual matches played (tournaments + scrims)")

    last_updated = models.DateTimeField(auto_now=True)

    def update_total_points(self):
        """Calculate and update total points"""
        self.total_points = self.total_position_points + self.total_kill_points
        self.save()

    def __str__(self):
        return f"{self.team.name} - {self.game_name} - Rank #{self.rank}"

    class Meta:
        db_table = "team_statistics"
        unique_together = ('team', 'game_name')
        ordering = ['-total_points']
        verbose_name_plural = "Team Statistics"


class TeamMember(models.Model):
    """
    Members of a team
    """

    ROLE_CHOICES = [
        ('IGL', 'IGL'),
        ('Assaulter', 'Assaulter'),
        ('Support', 'Support'),
        ('Scout', 'Scout'),
        ('Sniper', 'Sniper'),
        ('Rusher', 'Rusher'),
        ('Duelist', 'Duelist'),
        ('Controller', 'Controller'),
        ('Sentinel', 'Sentinel'),
        ('Initiator', 'Initiator'),
        ('Flex', 'Flex'),
        ('Member', 'Member'),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    # Link to user if they are registered, otherwise just use username
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="team_memberships")
    username = models.CharField(max_length=100)
    is_captain = models.BooleanField(default=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='Member', blank=True)
    is_temporary = models.BooleanField(
        default=False,
        help_text="True if this membership is temporary for the current user — set when they joined this team "
                  "while already having a permanent team for the same game. They get the convert/decline prompt."
    )
    conversion_deadline = models.DateTimeField(
        null=True, blank=True,
        help_text="48h window for this member to keep this team permanently (only set when is_temporary=True)"
    )

    def __str__(self):
        return f"{self.username} in {self.team.name}"

    class Meta:
        db_table = "team_members"
        unique_together = ("team", "username")


class TeamJoinRequest(models.Model):
    """
    Join requests for teams
    """

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    )

    TYPE_CHOICES = (
        ("request", "Request"),
        ("invite", "Invite"),
    )

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="join_requests")
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name="team_join_requests", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="request")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # NEW FIELDS FOR INVITE-BASED REGISTRATION
    invite_token = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True, help_text="Unique token for email-based invites")
    invited_email = models.EmailField(null=True, blank=True, help_text="Email address of the invited player")
    invite_expires_at = models.DateTimeField(null=True, blank=True, help_text="Expiration time for the invite")
    tournament_registration = models.ForeignKey('tournaments.TournamentRegistration', on_delete=models.CASCADE, null=True, blank=True, related_name='join_requests', help_text="Link to the tournament registration")

    INVITE_TYPE_CHOICES = (
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('username', 'Username'),
        ('link', 'Link'),
    )
    invite_type = models.CharField(max_length=20, choices=INVITE_TYPE_CHOICES, null=True, blank=True, help_text="How the invite was sent")
    phone_number = models.CharField(max_length=20, null=True, blank=True, help_text="Phone number for SMS invites")

    def __str__(self):
        if self.player:
            return f"{self.player.username} -> {self.team.name} ({self.status})"
        return f"(no player) -> {self.team.name} ({self.status})"

    class Meta:
        db_table = "team_join_requests"
        ordering = ["-created_at"]


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('team_invite', 'Team Invite'),
        ('match_start', 'Match Starting Soon'),
        ('credential_release', 'Credentials Released'),
        ('slot_list', 'Slot List Published'),
        ('results', 'Results Published'),
        ('teammate_joined', 'Teammate Joined'),
        ('tournament_update', 'Tournament Update'),
        ('registration_confirmed', 'Registration Confirmed'),
        ('general', 'General'),
        ('team_conversion_offer', 'Team Conversion Offer'),
        ('team_conversion_reminder', 'Team Conversion Reminder'),
        ('team_deleted', 'Team Deleted'),
        # Player-specific notification types
        ('payment_confirmed', 'Payment Confirmed'),
        ('points_entered', 'Match Points Entered'),
        ('tournament_result', 'Tournament Result'),
        ('slot_list_release', 'Slot List Released'),
        # Host-specific notification types
        ('new_registration', 'New Team Registration'),
        ('slots_full', 'Tournament Slots Full'),
        ('verification_approved', 'Verification Approved'),
        ('verification_rejected', 'Verification Rejected'),
        ('tournament_start_reminder', 'Tournament Starting Soon'),
        ('payment_received', 'Payment Received'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, default='general')
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # Optional link data
    related_id = models.IntegerField(null=True, blank=True)  # tournament/team id
    related_type = models.CharField(max_length=30, blank=True, default='')  # 'tournament', 'team'

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.type}] {self.title} → {self.user.username}"


class DataExportRequest(models.Model):
    """
    Stores a user's data export request with a signed token.
    The token is used to access the exported data via email link (no auth needed).
    Expires after 7 days.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='data_exports')
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        """Check if this export request is still valid (not expired)."""
        return not self.is_used and self.expires_at > timezone.now()

    def save(self, *args, **kwargs):
        # Auto-set expires_at to 7 days from creation if not set
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"DataExport for {self.user.username} ({self.token})"

    class Meta:
        db_table = "data_export_requests"
        ordering = ["-created_at"]
