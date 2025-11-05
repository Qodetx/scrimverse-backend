from django.contrib import admin

from .models import HostRating, Scrim, ScrimRegistration, Tournament, TournamentRegistration


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "host",
        "game_name",
        "status",
        "current_participants",
        "max_participants",
        "prize_pool",
        "tournament_start",
    )
    list_filter = ("status", "game_name", "is_featured")
    search_fields = ("title", "game_name", "host__organization_name")
    ordering = ("-created_at",)


@admin.register(Scrim)
class ScrimAdmin(admin.ModelAdmin):
    list_display = ("title", "host", "game_name", "status", "current_participants", "max_participants", "scrim_start")
    list_filter = ("status", "game_name", "is_featured")
    search_fields = ("title", "game_name", "host__organization_name")
    ordering = ("-created_at",)


@admin.register(TournamentRegistration)
class TournamentRegistrationAdmin(admin.ModelAdmin):
    list_display = ("tournament", "player", "team_name", "status", "payment_status", "registered_at")
    list_filter = ("status", "payment_status")
    search_fields = ("tournament__title", "player__in_game_name", "team_name")


@admin.register(ScrimRegistration)
class ScrimRegistrationAdmin(admin.ModelAdmin):
    list_display = ("scrim", "player", "team_name", "status", "payment_status", "registered_at")
    list_filter = ("status", "payment_status")
    search_fields = ("scrim__title", "player__in_game_name", "team_name")


@admin.register(HostRating)
class HostRatingAdmin(admin.ModelAdmin):
    list_display = ("host", "player", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("host__organization_name", "player__in_game_name")
