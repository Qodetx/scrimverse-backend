from django.db import models
from django.db.models import Sum
from django.utils import timezone

from accounts.models import HostProfile, PlayerProfile, Team


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
        ("COD", "Call of Duty"),
        ("Freefire", "Free Fire"),
        ("Scarfall", "Scarfall"),
    )

    GAME_FORMAT_CHOICES = (
        ("Squad", "Squad"),
        ("Duo", "Duo"),
        ("Solo", "Solo"),
    )

    PLAN_CHOICES = (
        ("basic", "Basic Listing - ₹299"),
        ("featured", "Featured Listing - ₹499"),
        ("premium", "Premium + Promotion - ₹799"),
    )

    EVENT_MODE_CHOICES = (
        ("TOURNAMENT", "Tournament"),
        ("SCRIM", "Scrim"),
    )

    # Event Mode - determines if this is a tournament or scrim
    event_mode = models.CharField(
        max_length=20,
        choices=EVENT_MODE_CHOICES,
        default="TOURNAMENT",
        help_text="Event type: Tournament (competitive) or Scrim (practice)",
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
    prize_pool = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Scrim-specific: Maximum number of matches (enforced for scrims, max 6)
    max_matches = models.IntegerField(
        default=6, help_text="Maximum number of matches (for scrims, max 6; for tournaments, based on rounds)"
    )

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

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="upcoming")
    is_featured = models.BooleanField(default=False)

    # Tournament Plan & Pricing
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES, default="basic", help_text="Tournament plan type")
    plan_price = models.DecimalField(max_digits=10, decimal_places=2, default=299.00, help_text="Plan price in INR")
    plan_payment_status = models.BooleanField(default=False, help_text="Whether plan payment is completed")
    plan_payment_id = models.CharField(max_length=100, blank=True, help_text="Payment transaction ID for plan")

    # Premium Features
    homepage_banner = models.BooleanField(
        default=False, help_text="Show on homepage banner (Featured and Premium plans)"
    )
    promotional_content = models.TextField(blank=True, help_text="Custom promotional content (Premium plan only)")
    visibility_boost_end = models.DateTimeField(
        blank=True, null=True, help_text="Extended visibility period end date (Premium plan)"
    )

    # System Flags
    use_groups_system = models.BooleanField(
        default=True, help_text="Use new groups and matches system (False for legacy tournaments)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.game_name}"

    def get_total_rounds(self):
        """Get total number of rounds"""
        return len(self.rounds) if self.rounds else 0

    def save(self, *args, **kwargs):
        """Override save to auto-update status and handle plan logic"""
        # Set plan price based on plan type
        plan_prices = {
            "basic": 299.00,
            "featured": 499.00,
            "premium": 799.00,
        }
        if self.plan_type in plan_prices:
            self.plan_price = plan_prices[self.plan_type]

        # Enforce max participants for basic plan
        if self.plan_type == "basic" and self.max_participants > 100:
            self.max_participants = 100

        if self.event_mode == "SCRIM":
            # Force Scrim Rules
            self.max_participants = min(self.max_participants, 25)
            self.max_matches = min(self.max_matches, 4)
            self.plan_type = "basic"

            # Force 1 Round structure
            self.rounds = [
                {
                    "round": 1,
                    "max_teams": self.max_participants,
                    "qualifying_teams": 0,  # 0 indicates final round / no qualification logic
                }
            ]

            # Scrims don't get featured status usually unless manually set,
            # but following the existing logic:
            self.is_featured = False
        else:
            # Auto-set is_featured for featured and premium plans
            if self.plan_type in ["featured", "premium"]:
                self.is_featured = True
            else:
                self.is_featured = False

        # Auto-update status on save
        if self.pk and "status" not in kwargs.get("update_fields", []):
            now = timezone.now()

            if self.tournament_start <= now < self.tournament_end:
                self.status = "ongoing"
            elif now >= self.tournament_end:
                self.status = "completed"

        super().save(*args, **kwargs)

    def can_modify_scrim_structure(self):
        """
        Check if scrim structure (match count, teams, etc.) can be modified.
        For scrims: Structure is locked once the first match starts.
        Returns: (bool, str) - (can_modify, reason)
        """
        if self.event_mode != "SCRIM":
            return True, "Not a scrim"

        # Check if any match has started
        first_match_started = Match.objects.filter(group__tournament=self, status__in=["live", "completed"]).exists()

        if first_match_started:
            return False, "Cannot modify scrim structure after first match has started"

        return True, "Scrim structure can be modified"

    class Meta:
        db_table = "tournaments"
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
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="tournament_registrations"
    )

    # Player Details for Tournament
    team_name = models.CharField(max_length=100, blank=True)
    team_members = models.JSONField(default=list, blank=True)  # List of player details

    # Registration Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="confirmed")
    payment_status = models.BooleanField(default=False)
    payment_id = models.CharField(max_length=100, blank=True)

    # Metadata
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.player.user.username} - {self.tournament.title}"

    class Meta:
        db_table = "tournament_registrations"
        unique_together = ("tournament", "player")
        ordering = ["-registered_at"]


class RoundScore(models.Model):
    """
    Aggregate scores for a team in a round (sum of all match scores)
    """

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

    def calculate_from_matches(self):
        """
        Calculate total points from all match scores in this round's groups
        """
        match_totals = MatchScore.objects.filter(
            match__group__tournament=self.tournament, match__group__round_number=self.round_number, team=self.team
        ).aggregate(total_pp=Sum("position_points"), total_kp=Sum("kill_points"))
        self.position_points = match_totals["total_pp"] or 0
        self.kill_points = match_totals["total_kp"] or 0
        self.total_points = self.position_points + self.kill_points
        self.save()


class Group(models.Model):
    """
    Tournament round group for organizing teams
    """

    STATUS_CHOICES = (
        ("waiting", "Waiting"),
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
    )

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="groups")
    round_number = models.IntegerField()
    group_name = models.CharField(max_length=50)  # "Group A", "Group B", etc.
    teams = models.ManyToManyField(TournamentRegistration, related_name="tournament_groups")
    qualifying_teams = models.IntegerField(default=0, help_text="Number of teams that qualify from this group")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waiting")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tournament", "round_number", "group_name")
        db_table = "tournament_groups"
        ordering = ["round_number", "group_name"]

    def __str__(self):
        return f"{self.tournament.title} - Round {self.round_number} - {self.group_name}"

    def is_completed(self):
        """Check if all matches in this group are completed"""
        return self.matches.filter(status="completed").count() == self.matches.count()

    def get_qualified_teams(self):
        """Get the top K teams from this group based on round scores"""
        # Get all teams in this group with their total points
        team_scores = []
        for team in self.teams.all():
            total = (
                MatchScore.objects.filter(match__group=self, team=team).aggregate(total=Sum("total_points"))["total"]
                or 0
            )

            team_scores.append({"team": team, "total_points": total})

        # Sort by total points descending
        team_scores.sort(key=lambda x: x["total_points"], reverse=True)

        # Return top K teams
        return [ts["team"] for ts in team_scores[: self.qualifying_teams]]


class Match(models.Model):
    """
    Individual match within a group
    """

    STATUS_CHOICES = (
        ("waiting", "Waiting"),
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
    )

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="matches")
    match_number = models.IntegerField()  # 1, 2, 3, 4...
    match_id = models.CharField(max_length=100, blank=True, help_text="Room ID for the match")
    match_password = models.CharField(max_length=100, blank=True, help_text="Password for the match room")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waiting")
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("group", "match_number")
        db_table = "tournament_matches"
        ordering = ["group", "match_number"]

    def __str__(self):
        return f"{self.group.group_name} - Match {self.match_number}"


class MatchScore(models.Model):
    """
    Team scores for a specific match
    Note: Wins (chicken dinners) are display-only, not counted in total points
    """

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="scores")
    team = models.ForeignKey(TournamentRegistration, on_delete=models.CASCADE, related_name="match_scores")
    wins = models.IntegerField(default=0, help_text="Number of chicken dinners (display only, not counted in total)")
    position_points = models.IntegerField(default=0)
    kill_points = models.IntegerField(default=0)
    total_points = models.IntegerField(default=0)

    class Meta:
        unique_together = ("match", "team")
        db_table = "tournament_match_scores"
        ordering = ["-total_points"]

    def save(self, *args, **kwargs):
        # Total = Position Points + Kill Points only (wins not counted)
        self.total_points = self.position_points + self.kill_points
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.team.team_name} - {self.match} - {self.total_points} pts"


class HostRating(models.Model):
    """
    Player ratings for hosts
    """

    host = models.ForeignKey(HostProfile, on_delete=models.CASCADE, related_name="ratings")
    player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name="host_ratings")
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, null=True, blank=True)

    rating = models.IntegerField()  # 1-5 stars
    review = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.player.user.username} rated {self.host.user.username}: {self.rating}/5"

    class Meta:
        db_table = "host_ratings"
        ordering = ["-created_at"]
