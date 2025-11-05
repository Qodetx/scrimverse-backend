from django.db import models

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

    host = models.ForeignKey(HostProfile, on_delete=models.CASCADE, related_name="tournaments")
    title = models.CharField(max_length=200)
    description = models.TextField()
    game_name = models.CharField(max_length=100)
    game_mode = models.CharField(max_length=100)  # e.g., "Squad", "Solo", "Duo"

    # Tournament Details
    max_participants = models.IntegerField()
    current_participants = models.IntegerField(default=0)
    entry_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    prize_pool = models.DecimalField(max_digits=10, decimal_places=2)

    # Prize Distribution (stored as JSON)
    prize_distribution = models.JSONField(default=dict)  # {"1st": 5000, "2nd": 3000, "3rd": 2000}

    # Tournament Schedule
    registration_start = models.DateTimeField()
    registration_end = models.DateTimeField()
    tournament_start = models.DateTimeField()
    tournament_end = models.DateTimeField()

    # Additional Info
    rules = models.TextField(blank=True)
    requirements = models.JSONField(default=list, blank=True)  # ["Level 40+", "KD > 2.0"]
    banner_image = models.ImageField(upload_to="tournaments/", blank=True, null=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="upcoming")
    is_featured = models.BooleanField(default=False)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.game_name}"

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
