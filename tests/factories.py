"""
Factory Boy factories for creating test data
"""
from datetime import timedelta

from django.utils import timezone

import factory
from factory.django import DjangoModelFactory
from faker import Faker

from accounts.models import HostProfile, PlayerProfile, Team, TeamStatistics, User
from tournaments.models import HostRating, Scrim, ScrimRegistration, Tournament, TournamentRegistration

fake = Faker()


class UserFactory(DjangoModelFactory):
    """Factory for User model"""

    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@test.com")
    username = factory.Sequence(lambda n: f"user{n}")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    user_type = "player"
    is_active = True
    is_staff = False
    is_superuser = False


class PlayerProfileFactory(DjangoModelFactory):
    """Factory for PlayerProfile model"""

    class Meta:
        model = PlayerProfile

    user = factory.SubFactory(UserFactory, user_type="player")
    bio = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=200))


class HostProfileFactory(DjangoModelFactory):
    """Factory for HostProfile model"""

    class Meta:
        model = HostProfile

    user = factory.SubFactory(UserFactory, user_type="host")
    bio = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=300))
    website = factory.LazyAttribute(lambda _: fake.url())
    rating = 4.5


class TournamentFactory(DjangoModelFactory):
    """Factory for Tournament model"""

    class Meta:
        model = Tournament

    host = factory.SubFactory(HostProfileFactory)
    title = factory.LazyAttribute(lambda _: f"{fake.catch_phrase()} Tournament")
    description = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=500))
    game_name = factory.Iterator(["BGMI", "COD", "Freefire", "Scarfall"])
    game_mode = "Squad"  # Default to Squad mode for consistent testing
    max_participants = factory.Iterator([50, 100, 150, 200])
    current_participants = 0
    entry_fee = factory.LazyAttribute(lambda _: fake.pydecimal(left_digits=3, right_digits=2, positive=True))
    prize_pool = factory.LazyAttribute(lambda _: fake.pydecimal(left_digits=5, right_digits=2, positive=True))

    @factory.lazy_attribute
    def registration_start(self):
        return timezone.now()

    @factory.lazy_attribute
    def registration_end(self):
        return self.registration_start + timedelta(days=5)

    @factory.lazy_attribute
    def tournament_start(self):
        return self.registration_end + timedelta(days=1)

    @factory.lazy_attribute
    def tournament_end(self):
        return self.tournament_start + timedelta(hours=6)

    status = "upcoming"
    rules = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=500))
    banner_image = None
    tournament_file = None

    @factory.lazy_attribute
    def tournament_date(self):
        return (timezone.now() + timedelta(days=7)).date()

    @factory.lazy_attribute
    def tournament_time(self):
        return timezone.now().time()

    @factory.lazy_attribute
    def rounds(self):
        """Generate 3-round structure"""
        return [
            {"round": 1, "max_teams": self.max_participants, "qualifying_teams": self.max_participants // 2},
            {"round": 2, "max_teams": self.max_participants // 2, "qualifying_teams": 10},
            {"round": 3, "max_teams": 10, "qualifying_teams": 1},
        ]


class ScrimFactory(DjangoModelFactory):
    """Factory for Scrim model"""

    class Meta:
        model = Scrim

    host = factory.SubFactory(HostProfileFactory)
    title = factory.LazyAttribute(lambda _: f"{fake.catch_phrase()} Scrim")
    description = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=300))
    game_name = factory.Iterator(["BGMI", "COD", "Freefire", "Scarfall"])
    game_mode = factory.Iterator(["Solo", "Duo", "Squad"])
    max_participants = factory.Iterator([20, 30, 50])
    current_participants = 0
    entry_fee = factory.LazyAttribute(lambda _: fake.pydecimal(left_digits=2, right_digits=2, positive=True))

    @factory.lazy_attribute
    def registration_start(self):
        return timezone.now()

    @factory.lazy_attribute
    def registration_end(self):
        return self.registration_start + timedelta(hours=2)

    @factory.lazy_attribute
    def scrim_start(self):
        return self.registration_end + timedelta(hours=1)

    @factory.lazy_attribute
    def scrim_end(self):
        return self.scrim_start + timedelta(hours=2)

    status = "upcoming"
    rules = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=200))


class TournamentRegistrationFactory(DjangoModelFactory):
    """Factory for TournamentRegistration model"""

    class Meta:
        model = TournamentRegistration

    tournament = factory.SubFactory(TournamentFactory)
    player = factory.SubFactory(PlayerProfileFactory)
    team_name = factory.LazyAttribute(lambda _: fake.company())

    @factory.lazy_attribute
    def team_members(self):
        return [fake.name() for _ in range(4)]

    payment_status = False
    status = "pending"


class ScrimRegistrationFactory(DjangoModelFactory):
    """Factory for ScrimRegistration model"""

    class Meta:
        model = ScrimRegistration

    scrim = factory.SubFactory(ScrimFactory)
    player = factory.SubFactory(PlayerProfileFactory)
    team_name = factory.LazyAttribute(lambda _: fake.company())

    @factory.lazy_attribute
    def team_members(self):
        return [fake.name() for _ in range(2)]

    status = "confirmed"


class HostRatingFactory(DjangoModelFactory):
    """Factory for HostRating model"""

    class Meta:
        model = HostRating

    host = factory.SubFactory(HostProfileFactory)
    player = factory.SubFactory(PlayerProfileFactory)
    rating = factory.Iterator([1, 2, 3, 4, 5])
    review = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=200))


class TeamFactory(DjangoModelFactory):
    """Factory for Team model"""

    class Meta:
        model = Team

    name = factory.LazyAttribute(lambda _: f"{fake.word().capitalize()} {fake.word().capitalize()}")
    captain = factory.SubFactory(UserFactory, user_type="player")
    description = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=200))
    is_temporary = False


class TeamStatisticsFactory(DjangoModelFactory):
    """Factory for TeamStatistics model"""

    class Meta:
        model = TeamStatistics

    team = factory.SubFactory(TeamFactory)
    tournament_position_points = 0
    tournament_kill_points = 0
    tournament_wins = 0
    tournament_rank = 0
    scrim_position_points = 0
    scrim_kill_points = 0
    scrim_wins = 0
    scrim_rank = 0
