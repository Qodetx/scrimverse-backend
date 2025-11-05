from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import HostProfile, PlayerProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "username", "user_type", "is_staff", "created_at")
    list_filter = ("user_type", "is_staff", "is_active")
    search_fields = ("email", "username")
    ordering = ("-created_at",)

    fieldsets = BaseUserAdmin.fieldsets + (
        ("Custom Fields", {"fields": ("user_type", "phone_number", "profile_picture")}),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Custom Fields", {"fields": ("email", "user_type", "phone_number")}),
    )


@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = ("in_game_name", "game_id", "total_tournaments_participated", "total_wins", "wallet_balance")
    search_fields = ("in_game_name", "game_id", "user__email")
    list_filter = ("skill_level",)


@admin.register(HostProfile)
class HostProfileAdmin(admin.ModelAdmin):
    list_display = ("organization_name", "user", "total_tournaments_hosted", "rating", "verified")
    search_fields = ("organization_name", "user__email")
    list_filter = ("verified", "rating")
