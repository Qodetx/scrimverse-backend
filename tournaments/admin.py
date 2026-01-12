from django.contrib import admin

from tournaments.models import (
    Group,
    HostRating,
    Match,
    MatchScore,
    RoundScore,
    Scrim,
    ScrimRegistration,
    Tournament,
    TournamentRegistration,
)


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "host",
        "game_name",
        "status",
        "plan_type",
        "plan_payment_status",
        "current_participants",
        "max_participants",
        "prize_pool",
        "tournament_start",
    )
    list_filter = ("status", "game_name", "is_featured", "plan_type", "plan_payment_status")
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


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("group_name", "tournament", "round_number", "created_at")
    list_filter = ("round_number",)
    search_fields = ("group_name", "tournament__title")
    ordering = ("tournament", "round_number", "group_name")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "group", "match_number", "status", "match_id", "started_at", "ended_at")
    list_filter = ("status",)
    search_fields = ("group__group_name", "match_id")
    ordering = ("group", "match_number")


@admin.register(MatchScore)
class MatchScoreAdmin(admin.ModelAdmin):
    list_display = ("team", "match", "wins", "position_points", "kill_points", "total_points")
    list_filter = ("match__status",)
    search_fields = ("team__team_name", "match__group__group_name")
    ordering = ("-total_points",)


@admin.register(RoundScore)
class RoundScoreAdmin(admin.ModelAdmin):
    list_display = ("team", "tournament", "round_number", "position_points", "kill_points", "total_points")
    list_filter = ("round_number",)
    search_fields = ("team__team_name", "tournament__title")
    ordering = ("tournament", "round_number", "-total_points")
