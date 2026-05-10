from django.conf import settings
from django.db import models


class CommunitySettings(models.Model):
    """
    Singleton model — only one row (pk=1) ever exists.
    Admin sets WhatsApp and Instagram community links here.
    Hosts cannot access or edit this.
    """

    whatsapp_link = models.URLField(blank=True, default="", help_text="WhatsApp community invite link")
    instagram_link = models.URLField(blank=True, default="", help_text="Instagram profile or community link")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Community Settings"
        verbose_name_plural = "Community Settings"

    def __str__(self):
        return "Community Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # Prevent deletion of the singleton

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class CommunityJoin(models.Model):
    """
    Records when a registered user clicks a community join button (WhatsApp / Instagram).
    Used to track who has and hasn't joined, and to generate follow-up lists.
    """

    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    COMMUNITY_CHOICES = [
        (WHATSAPP, "WhatsApp"),
        (INSTAGRAM, "Instagram"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_joins",
    )
    community_type = models.CharField(max_length=20, choices=COMMUNITY_CHOICES)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "community_type")
        verbose_name = "Community Join"
        verbose_name_plural = "Community Joins"
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user} → {self.get_community_type_display()} ({self.joined_at.date()})"
