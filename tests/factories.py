"""
Factory Boy factories for creating test data
"""
from datetime import timedelta

from django.utils import timezone

import factory
from factory.django import DjangoModelFactory
from faker import Faker

from accounts.models import HostProfile, PlayerProfile, User
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
    in_game_name = factory.LazyAttribute(lambda _: fake.user_name())
    game_id = factory.Sequence(lambda n: f"UID{n:06d}")
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
    game_name = factory.Iterator(["BGMI", "Free Fire", "Call of Duty", "Valorant", "PUBG"])
    game_mode = factory.Iterator(["Solo", "Duo", "Squad", "Team"])
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


class ScrimFactory(DjangoModelFactory):
    """Factory for Scrim model"""

    class Meta:
        model = Scrim

    host = factory.SubFactory(HostProfileFactory)
    title = factory.LazyAttribute(lambda _: f"{fake.catch_phrase()} Scrim")
    description = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=300))
    game_name = factory.Iterator(["BGMI", "Free Fire", "Call of Duty", "Valorant"])
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

    @factory.lazy_attribute
    def in_game_details(self):
        return {"ign": fake.user_name(), "uid": f"UID{fake.random_number(digits=6)}", "rank": "Gold"}

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

    @factory.lazy_attribute
    def in_game_details(self):
        return {"ign": fake.user_name(), "uid": f"UID{fake.random_number(digits=6)}"}

    status = "confirmed"


class HostRatingFactory(DjangoModelFactory):
    """Factory for HostRating model"""

    class Meta:
        model = HostRating

    host = factory.SubFactory(HostProfileFactory)
    player = factory.SubFactory(PlayerProfileFactory)
    rating = factory.Iterator([1, 2, 3, 4, 5])
    review = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=200))
