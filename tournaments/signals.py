"""
Signal handlers for tournament cache invalidation
"""
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from tournaments.models import Tournament, TournamentRegistration


@receiver(post_save, sender=Tournament)
def invalidate_tournament_cache_on_save(sender, instance, **kwargs):
    """Clear tournament list cache when a tournament is created or updated"""
    cache.delete("tournaments:list:all")


@receiver(post_delete, sender=Tournament)
def invalidate_tournament_cache_on_delete(sender, instance, **kwargs):
    """Clear tournament list cache when a tournament is deleted"""
    cache.delete("tournaments:list:all")


@receiver(post_save, sender=TournamentRegistration)
def invalidate_tournament_cache_on_registration(sender, instance, **kwargs):
    """Clear tournament list cache when a player registers (participant count changes)"""
    cache.delete("tournaments:list:all")
