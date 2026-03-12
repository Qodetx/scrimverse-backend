from tournaments.models import Tournament, TournamentRegistration
from accounts.models import PlayerProfile, User

# Number of registrations to create
DESIRED_REGISTRATIONS = 8

# Find a COD tournament
tournament = Tournament.objects.filter(game_name__in=["COD", "Call of Duty"]).first()
if not tournament:
    print("No COD tournament found. Exiting.")
else:
    players = list(PlayerProfile.objects.all()[:DESIRED_REGISTRATIONS])

    # Create missing player accounts if needed
    next_idx = 1
    if len(players) < DESIRED_REGISTRATIONS:
        start = len(players) + 1
        for i in range(start, DESIRED_REGISTRATIONS + 1):
            username = f"autocod{i}"
            email = f"{username}@example.com"
            # Create user; create_user should accept extra fields on custom user model
            user = User.objects.create_user(username=username, email=email, password="password", user_type="player", phone_number="9999999999")
            pp = PlayerProfile.objects.create(user=user)
            players.append(pp)

    created = []
    for idx, pp in enumerate(players, start=1):
        tr, was_created = TournamentRegistration.objects.get_or_create(
            tournament=tournament,
            player=pp,
            defaults={
                "team_name": f"AutoTeam_COD_{idx}",
                "team_members": [pp.user.username],
                "status": "confirmed",
                "payment_status": True,
            },
        )
        created.append((tr, was_created))

    # Update tournament participant count
    tournament.current_participants = tournament.registrations.count()
    tournament.save(update_fields=["current_participants"])

    print(f"Tournament ID: {tournament.id} - {tournament.title} ({tournament.game_name})")
    print(f"Total registrations now: {tournament.current_participants}")
    for tr, was_created in created:
        print(f"RegID: {tr.id} | Team: {tr.team_name} | Player: {tr.player.user.username} | Created: {was_created}")
