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
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    profile_picture = models.ImageField(upload_to="profiles/", blank=True, null=True)
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
    in_game_name = models.CharField(max_length=100)
    game_id = models.CharField(max_length=100)
    preferred_games = models.JSONField(default=list, blank=True)  # List of games
    skill_level = models.CharField(max_length=50, blank=True)
    bio = models.TextField(blank=True)
    total_tournaments_participated = models.IntegerField(default=0)
    total_wins = models.IntegerField(default=0)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"Player: {self.in_game_name}"

    class Meta:
        db_table = "player_profiles"


class HostProfile(models.Model):
    """
    Extended profile for hosts/organizers
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="host_profile")
    organization_name = models.CharField(max_length=200, blank=True)
    bio = models.TextField(blank=True)
    website = models.URLField(blank=True)
    social_links = models.JSONField(default=dict, blank=True)  # {"twitter": "", "discord": ""}
    total_tournaments_hosted = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)  # Out of 5
    total_ratings = models.IntegerField(default=0)
    verified = models.BooleanField(default=False)

    def __str__(self):
        return f"Host: {self.organization_name or self.user.username}"

    class Meta:
        db_table = "host_profiles"
