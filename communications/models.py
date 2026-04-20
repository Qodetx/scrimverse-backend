from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class BroadcastEmail(models.Model):
    RECIPIENT_TYPE_CHOICES = [
        ("all_users", "All Users (Players + Hosts)"),
        ("all_players", "All Players"),
        ("all_hosts", "All Hosts"),
        ("tournament_participants", "Tournament Participants"),
        ("individual_users", "Individual Users"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sending", "Sending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    TOURNAMENT_STATUS_FILTER_CHOICES = [
        ("all", "All Tournaments"),
        ("upcoming", "Upcoming"),
        ("ongoing", "Ongoing (Live)"),
        ("completed", "Completed"),
    ]

    subject = models.CharField(max_length=255)
    body = models.TextField(help_text="Plain text email body. You can include links by pasting full URLs.")

    recipient_type = models.CharField(
        max_length=30,
        choices=RECIPIENT_TYPE_CHOICES,
        default="all_players",
    )

    # Used when recipient_type = tournament_participants
    selected_tournaments = models.ManyToManyField(
        "tournaments.Tournament",
        blank=True,
        help_text=(
            "Select specific tournaments. Leave empty to target ALL tournaments "
            "(filtered by tournament status filter below)."
        ),
    )
    tournament_status_filter = models.CharField(
        max_length=20,
        choices=TOURNAMENT_STATUS_FILTER_CHOICES,
        default="all",
        help_text=(
            "Only used when recipient type is 'Tournament Participants'. "
            "Filter which tournaments to include when no specific tournaments are selected."
        ),
    )

    # Used when recipient_type = individual_users
    selected_users = models.ManyToManyField(
        User,
        blank=True,
        related_name="broadcast_emails",
        help_text="Select specific users to send this email to.",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    total_sent = models.IntegerField(default=0, help_text="Number of emails successfully sent.")
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error details if sending failed.",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_broadcasts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Broadcast Email"
        verbose_name_plural = "Broadcast Emails"

    def __str__(self):
        return f"[{self.status.upper()}] {self.subject} ({self.get_recipient_type_display()})"
