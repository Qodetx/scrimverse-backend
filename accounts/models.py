from django.contrib.auth.models import AbstractUser
from django.db import models


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
    phone_number = models.CharField(max_length=10)
    profile_picture = models.ImageField(upload_to="profiles/", blank=True, null=True)
    username_change_count = models.IntegerField(default=0)
    last_username_change = models.DateTimeField(null=True, blank=True)
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
    preferred_games = models.JSONField(default=list, blank=True)  # List of games
    skill_level = models.CharField(max_length=50, blank=True)
    bio = models.TextField(blank=True)
    total_tournaments_participated = models.IntegerField(default=0)
    total_wins = models.IntegerField(default=0)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"Player: {self.user.username}"

    class Meta:
        db_table = "player_profiles"


class HostProfile(models.Model):
    """
    Extended profile for hosts/organizers
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="host_profile")
    bio = models.TextField(blank=True)
    website = models.URLField(blank=True)
    social_links = models.JSONField(default=dict, blank=True)  # {"twitter": "", "discord": ""}
    total_tournaments_hosted = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)  # Out of 5
    total_ratings = models.IntegerField(default=0)
    verified = models.BooleanField(default=False)

    def __str__(self):
        return f"Host: {self.user.username}"

    class Meta:
        db_table = "host_profiles"


class Team(models.Model):
    """
    Team model for players to group up
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="WE ARE BEAST", help_text="Team tagline or description")
    profile_picture = models.ImageField(
        upload_to="teams/", blank=True, null=True, help_text="Team logo/profile picture"
    )
    captain = models.ForeignKey(User, on_delete=models.CASCADE, related_name="managed_teams")
    created_at = models.DateTimeField(auto_now_add=True)
    is_temporary = models.BooleanField(default=False, help_text="True if created for a single tournament")

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
    """

    team = models.OneToOneField(Team, on_delete=models.CASCADE, related_name="statistics")

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
    last_updated = models.DateTimeField(auto_now=True)

    def update_total_points(self):
        """Calculate and update total points"""
        self.total_points = self.total_position_points + self.total_kill_points
        self.save()

    def __str__(self):
        return f"{self.team.name} - Rank #{self.rank}"

    class Meta:
        db_table = "team_statistics"
        ordering = ["rank"]
        verbose_name_plural = "Team Statistics"


class TeamMember(models.Model):
    """
    Members of a team
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    # Link to user if they are registered, otherwise just use username
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="team_memberships")
    username = models.CharField(max_length=100)
    is_captain = models.BooleanField(default=False)

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
    )

    TYPE_CHOICES = (
        ("request", "Request"),
        ("invite", "Invite"),
    )

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="join_requests")
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name="team_join_requests")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="request")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.player.username} -> {self.team.name} ({self.status})"

    class Meta:
        db_table = "team_join_requests"
        unique_together = ("team", "player")
        ordering = ["-created_at"]
