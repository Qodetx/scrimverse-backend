#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration

def update_counts(tournament_id):
    try:
        tournament = Tournament.objects.get(id=tournament_id)
        registration_count = TournamentRegistration.objects.filter(
            tournament=tournament,
            status='confirmed'
        ).count()
        
        print(f"Tournament: {tournament.title} (ID: {tournament.id})")
        print(f"Current participants field: {tournament.current_participants}")
        print(f"Actual confirmed registrations: {registration_count}")
        
        if tournament.current_participants != registration_count:
            tournament.current_participants = registration_count
            tournament.save(update_fields=['current_participants', 'updated_at'])
            print(f"✅ Updated current_participants to {registration_count}")
        else:
            print("ℹ️ Counts are already correct.")
            
    except Tournament.DoesNotExist:
        print(f"❌ Tournament ID {tournament_id} not found!")

if __name__ == "__main__":
    update_counts(8)
