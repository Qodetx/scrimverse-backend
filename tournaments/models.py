from django.db import models
from django.utils import timezone

from accounts.models import HostProfile, PlayerProfile


class Tournament(models.Model):
    """
    Tournament model for competitive gaming events
    """

    STATUS_CHOICES = (
        ("upcoming", "Upcoming"),
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    )

    GAME_CHOICES = (
        ("BGMI", "BGMI"),
        ("Valorant", "Valorant"),
        ("COD", "Call of Duty"),
        ("Freefire", "Free Fire"),
        ("CS2", "Counter-Strike 2"),
    )

    GAME_FORMAT_CHOICES = (
        ("Squad", "Squad"),
        ("Duo", "Duo"),
        ("Solo", "Solo"),
    )

    host = models.ForeignKey(HostProfile, on_delete=models.CASCADE, related_name="tournaments")
    title = models.CharField(max_length=200)
    description = models.TextField(help_text="Tournament description")

    # Game Details
    game_name = models.CharField(max_length=100, choices=GAME_CHOICES)
    game_mode = models.CharField(max_length=100, choices=GAME_FORMAT_CHOICES)  # Squad, Solo, Duo

    # Tournament Details
    max_participants = models.IntegerField(help_text="Maximum number of teams")
    current_participants = models.IntegerField(default=0)
    entry_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    prize_pool = models.DecimalField(max_digits=10, decimal_places=2)

    # Prize Distribution (stored as JSON)
    prize_distribution = models.JSONField(default=dict, blank=True)  # {"1st": 5000, "2nd": 3000, "3rd": 2000}

    # Tournament Schedule
    tournament_date = models.DateField(help_text="Tournament date", null=True, blank=True)
    tournament_time = models.TimeField(help_text="Tournament start time", null=True, blank=True)
    registration_start = models.DateTimeField()
    registration_end = models.DateTimeField()
    tournament_start = models.DateTimeField()
    tournament_end = models.DateTimeField()

    # Rounds Structure - Dynamic rounds with qualification criteria
    rounds = models.JSONField(
        default=list,
        blank=True,
        help_text="Round structure: [{round: 1, max_teams: 100}, {round: 2, qualifying_teams: 50}, ...]",
    )
    # Example: [
    #   {"round": 1, "max_teams": 100, "qualifying_teams": 50},
    #   {"round": 2, "max_teams": 50, "qualifying_teams": 20},
    #   {"round": 3, "max_teams": 20, "qualifying_teams": 1}
    # ]

    # Round Management
    current_round = models.IntegerField(default=0, help_text="Current active round (0 = not started)")
    round_status = models.JSONField(
        default=dict, blank=True, help_text="Round status: {'1': 'completed', '2': 'ongoing', '3': 'upcoming'}"
    )
    selected_teams = models.JSONField(
        default=dict,
        blank=True,
        help_text="Selected teams per round: {'1': [reg_id1, reg_id2], '2': [reg_id3, reg_id4]}",
    )
    winners = models.JSONField(
        default=dict, blank=True, help_text="Winners per round: {'2': reg_id1} (final round winner)"
    )

    # Rules
    rules = models.TextField(help_text="Custom rules and regulations")
    requirements = models.JSONField(default=list, blank=True)  # ["Level 40+", "KD > 2.0"]

    # Files and Media
    tournament_file = models.FileField(
        upload_to="tournaments/files/", blank=True, null=True, help_text="Tournament rules PDF or document"
    )
    banner_image = models.ImageField(
        upload_to="tournaments/banners/", blank=True, null=True, help_text="Tournament banner image (max 5MB)"
    )

    # Contact
    discord_id = models.CharField(max_length=100, blank=True, help_text="Discord server ID (optional)")

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="upcoming")
    is_featured = models.BooleanField(default=False)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.game_name}"

    def get_total_rounds(self):
        """Get total number of rounds"""
        return len(self.rounds) if self.rounds else 0

    def save(self, *args, **kwargs):
        """Override save to auto-update status"""
        # Auto-update status on save
        if self.pk and "status" not in kwargs.get("update_fields", []):
            now = timezone.now()

            if self.tournament_start <= now < self.tournament_end:
                self.status = "ongoing"
            elif now >= self.tournament_end:
                self.status = "completed"

        super().save(*args, **kwargs)

    class Meta:
        db_table = "tournaments"
        ordering = ["-created_at"]


class Scrim(models.Model):
    """
    Scrim (Practice Match) model for casual gaming sessions
    """

    STATUS_CHOICES = (
        ("upcoming", "Upcoming"),
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    )

    host = models.ForeignKey(HostProfile, on_delete=models.CASCADE, related_name="scrims")
    title = models.CharField(max_length=200)
    description = models.TextField()
    game_name = models.CharField(max_length=100)
    game_mode = models.CharField(max_length=100)

    # Scrim Details
    max_participants = models.IntegerField()
    current_participants = models.IntegerField(default=0)
    entry_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Scrim Schedule
    registration_start = models.DateTimeField()
    registration_end = models.DateTimeField()
    scrim_start = models.DateTimeField()
    scrim_end = models.DateTimeField()

    # Additional Info
    rules = models.TextField(blank=True)
    requirements = models.JSONField(default=list, blank=True)
    banner_image = models.ImageField(upload_to="scrims/", blank=True, null=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="upcoming")
    is_featured = models.BooleanField(default=False)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.game_name}"

    class Meta:
        db_table = "scrims"
        ordering = ["-created_at"]


class TournamentRegistration(models.Model):
    """
    Registration for tournaments
    """

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    )

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="registrations")
    player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name="tournament_registrations")

    # Player Details for Tournament
    team_name = models.CharField(max_length=100, blank=True)
    team_members = models.JSONField(default=list, blank=True)  # List of player details
    in_game_details = models.JSONField(default=dict)  # {"ign": "", "uid": "", "rank": ""}

    # Registration Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    payment_status = models.BooleanField(default=False)
    payment_id = models.CharField(max_length=100, blank=True)

    # Metadata
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.player.in_game_name} - {self.tournament.title}"

    class Meta:
        db_table = "tournament_registrations"
        unique_together = ("tournament", "player")
        ordering = ["-registered_at"]


class RoundScore(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="round_scores")
    round_number = models.IntegerField()
    team = models.ForeignKey(TournamentRegistration, on_delete=models.CASCADE, related_name="round_scores")
    position_points = models.IntegerField(default=0)
    kill_points = models.IntegerField(default=0)
    total_points = models.IntegerField(default=0)

    class Meta:
        unique_together = ("tournament", "round_number", "team")
        db_table = "round_scores"

    def save(self, *args, **kwargs):
        self.total_points = self.position_points + self.kill_points
        super().save(*args, **kwargs)


class ScrimRegistration(models.Model):
    """
    Registration for scrims
    """

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    )

    scrim = models.ForeignKey(Scrim, on_delete=models.CASCADE, related_name="registrations")
    player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name="scrim_registrations")

    # Player Details for Scrim
    team_name = models.CharField(max_length=100, blank=True)
    team_members = models.JSONField(default=list, blank=True)
    in_game_details = models.JSONField(default=dict)

    # Registration Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    payment_status = models.BooleanField(default=False)
    payment_id = models.CharField(max_length=100, blank=True)

    # Metadata
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.player.in_game_name} - {self.scrim.title}"

    class Meta:
        db_table = "scrim_registrations"
        unique_together = ("scrim", "player")
        ordering = ["-registered_at"]


class HostRating(models.Model):
    """
    Player ratings for hosts
    """

    host = models.ForeignKey(HostProfile, on_delete=models.CASCADE, related_name="ratings")
    player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name="host_ratings")
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, null=True, blank=True)
    scrim = models.ForeignKey(Scrim, on_delete=models.CASCADE, null=True, blank=True)

    rating = models.IntegerField()  # 1-5 stars
    review = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.player.in_game_name} rated {self.host.organization_name}: {self.rating}/5"

    class Meta:
        db_table = "host_ratings"
