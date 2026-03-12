"""
Host Rating admin class.
"""
from django.contrib import admin
from django.utils.html import format_html

from tournaments.models import HostRating


@admin.register(HostRating)
class HostRatingAdmin(admin.ModelAdmin):
    """Enhanced Host Rating Admin with moderation features"""

    list_display = ["host_display", "player_display", "rating_stars", "tournament_display", "created_at"]
    list_filter = ["rating", ("created_at", admin.DateFieldListFilter)]
    search_fields = ["host__user__username", "player__user__username", "review"]
    readonly_fields = ["created_at"]

    actions = ["delete_selected_ratings", "export_ratings_csv"]

    def host_display(self, obj):
        """Display host with link"""
        return format_html(
            '<a href="/admin/accounts/hostprofile/{}/change/">{}</a>',
            obj.host.id,
            obj.host.user.username,
        )

    host_display.short_description = "Host"

    def player_display(self, obj):
        """Display player with link"""
        return format_html(
            '<a href="/admin/accounts/playerprofile/{}/change/">{}</a>',
            obj.player.id,
            obj.player.user.username,
        )

    player_display.short_description = "Player"

    def rating_stars(self, obj):
        """Display rating as stars"""
        stars = "⭐" * obj.rating
        color = "#ffc107" if obj.rating >= 4 else "#6c757d"
        return format_html(
            '<span style="color: {}; font-size: 16px;">{} ({})</span>',
            color,
            stars,
            obj.rating,
        )

    rating_stars.short_description = "Rating"

    def tournament_display(self, obj):
        """Display tournament if exists"""
        if obj.tournament:
            return format_html(
                '<a href="/admin/tournaments/tournament/{}/change/">{}</a>',
                obj.tournament.id,
                obj.tournament.title,
            )
        return "-"

    tournament_display.short_description = "Tournament"

    def delete_selected_ratings(self, request, queryset):
        """Delete selected ratings (for spam/inappropriate content)"""
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"{count} rating(s) deleted.")

    delete_selected_ratings.short_description = "Delete Selected Ratings"

    def export_ratings_csv(self, request, queryset):
        """Export ratings to CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="host_ratings.csv"'

        writer = csv.writer(response)
        writer.writerow(["Host", "Player", "Rating", "Review", "Tournament", "Date"])

        for rating in queryset:
            writer.writerow(
                [
                    rating.host.user.username,
                    rating.player.user.username,
                    rating.rating,
                    rating.review,
                    rating.tournament.title if rating.tournament else "N/A",
                    rating.created_at,
                ]
            )

        self.message_user(request, f"{queryset.count()} rating(s) exported to CSV.")
        return response

    export_ratings_csv.short_description = "Export to CSV"
