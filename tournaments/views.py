from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from django.db.models import Q
from django.core.cache import cache
from .models import Tournament, Scrim, TournamentRegistration, ScrimRegistration, HostRating
from accounts.models import HostProfile, PlayerProfile
from .serializers import (
    TournamentSerializer, TournamentListSerializer,
    ScrimSerializer, ScrimListSerializer,
    TournamentRegistrationSerializer, ScrimRegistrationSerializer,
    HostRatingSerializer
)


class IsHostUser(permissions.BasePermission):
    """Permission class for Host users"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'host'


class IsPlayerUser(permissions.BasePermission):
    """Permission class for Player users"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'player'


# ============= Tournament Views =============

class TournamentListView(generics.ListAPIView):
    """
    List all tournaments with Redis cache (Guest/Player/Host can access)
    GET /api/tournaments/
    Cache: Only when no filters applied
    """
    queryset = Tournament.objects.all()
    serializer_class = TournamentListSerializer
    permission_classes = [permissions.AllowAny]
    
    def list(self, request, *args, **kwargs):
        # Only cache if no query params (unfiltered list)
        status_param = request.query_params.get('status')
        game_param = request.query_params.get('game')
        
        if not status_param and not game_param:
            cache_key = 'tournaments:list:all'
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return Response(cached_data)
            
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            cache.set(cache_key, serializer.data, timeout=300)  # 5 minutes
            return Response(serializer.data)
        
        # Don't cache filtered results
        return super().list(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Tournament.objects.all()
        status = self.request.query_params.get('status', None)
        game = self.request.query_params.get('game', None)
        
        if status:
            queryset = queryset.filter(status=status)
        if game:
            queryset = queryset.filter(game_name__icontains=game)
        
        return queryset


class TournamentDetailView(generics.RetrieveAPIView):
    """
    Get tournament details
    GET /api/tournaments/<id>/
    """
    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [permissions.AllowAny]


class TournamentCreateView(generics.CreateAPIView):
    """
    Host creates a tournament
    POST /api/tournaments/create/
    Invalidates cache on creation
    """
    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]
    
    def perform_create(self, serializer):
        host_profile = HostProfile.objects.get(user=self.request.user)
        serializer.save(host=host_profile)
        # Invalidate tournament list cache
        cache.delete('tournaments:list:all')


class TournamentUpdateView(generics.UpdateAPIView):
    """
    Host updates their tournament
    PUT/PATCH /api/tournaments/<id>/update/
    Invalidates cache on update
    """
    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]
    
    def get_queryset(self):
        # Host can only update their own tournaments
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)
    
    def perform_update(self, serializer):
        serializer.save()
        # Invalidate cache
        cache.delete('tournaments:list:all')


class TournamentDeleteView(generics.DestroyAPIView):
    """
    Host deletes their tournament
    DELETE /api/tournaments/<id>/delete/
    Invalidates cache on deletion
    """
    queryset = Tournament.objects.all()
    permission_classes = [IsHostUser]
    
    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)
    
    def perform_destroy(self, instance):
        instance.delete()
        # Invalidate cache
        cache.delete('tournaments:list:all')


class HostTournamentsView(generics.ListAPIView):
    """
    Get all tournaments by a specific host
    GET /api/tournaments/host/<host_id>/
    """
    serializer_class = TournamentListSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        host_id = self.kwargs['host_id']
        return Tournament.objects.filter(host_id=host_id)


# ============= Scrim Views =============

class ScrimListView(generics.ListAPIView):
    """
    List all scrims
    GET /api/tournaments/scrims/
    """
    queryset = Scrim.objects.all()
    serializer_class = ScrimListSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        queryset = Scrim.objects.all()
        status = self.request.query_params.get('status', None)
        game = self.request.query_params.get('game', None)
        
        if status:
            queryset = queryset.filter(status=status)
        if game:
            queryset = queryset.filter(game_name__icontains=game)
        
        return queryset


class ScrimDetailView(generics.RetrieveAPIView):
    """
    Get scrim details
    GET /api/tournaments/scrims/<id>/
    """
    queryset = Scrim.objects.all()
    serializer_class = ScrimSerializer
    permission_classes = [permissions.AllowAny]


class ScrimCreateView(generics.CreateAPIView):
    """
    Host creates a scrim
    POST /api/tournaments/scrims/create/
    """
    serializer_class = ScrimSerializer
    permission_classes = [IsHostUser]
    
    def perform_create(self, serializer):
        host_profile = HostProfile.objects.get(user=self.request.user)
        serializer.save(host=host_profile)


class ScrimUpdateView(generics.UpdateAPIView):
    """
    Host updates their scrim
    PUT/PATCH /api/tournaments/scrims/<id>/update/
    """
    queryset = Scrim.objects.all()
    serializer_class = ScrimSerializer
    permission_classes = [IsHostUser]
    
    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Scrim.objects.filter(host=host_profile)


class ScrimDeleteView(generics.DestroyAPIView):
    """
    Host deletes their scrim
    DELETE /api/tournaments/scrims/<id>/delete/
    """
    queryset = Scrim.objects.all()
    permission_classes = [IsHostUser]
    
    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Scrim.objects.filter(host=host_profile)


# ============= Registration Views =============

class TournamentRegistrationCreateView(generics.CreateAPIView):
    """
    Player registers for a tournament
    POST /api/tournaments/<tournament_id>/register/
    Invalidates cache when participant count changes
    """
    serializer_class = TournamentRegistrationSerializer
    permission_classes = [IsPlayerUser]
    
    def perform_create(self, serializer):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        tournament_id = self.kwargs['tournament_id']
        tournament = Tournament.objects.get(id=tournament_id)
        
        # Check if already registered
        if TournamentRegistration.objects.filter(tournament=tournament, player=player_profile).exists():
            raise ValidationError({'error': 'Already registered for this tournament'})
        
        serializer.save(player=player_profile, tournament=tournament)
        
        # Update participant count
        tournament.current_participants += 1
        tournament.save()
        
        # Invalidate cache since participant count changed
        cache.delete('tournaments:list:all')


class ScrimRegistrationCreateView(generics.CreateAPIView):
    """
    Player registers for a scrim
    POST /api/tournaments/scrims/<scrim_id>/register/
    """
    serializer_class = ScrimRegistrationSerializer
    permission_classes = [IsPlayerUser]
    
    def perform_create(self, serializer):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        scrim_id = self.kwargs['scrim_id']
        scrim = Scrim.objects.get(id=scrim_id)
        
        # Check if already registered
        if ScrimRegistration.objects.filter(scrim=scrim, player=player_profile).exists():
            raise ValidationError({'error': 'Already registered for this scrim'})
        
        serializer.save(player=player_profile, scrim=scrim)
        
        # Update participant count
        scrim.current_participants += 1
        scrim.save()


class PlayerTournamentRegistrationsView(generics.ListAPIView):
    """
    Get all tournament registrations of a player
    GET /api/tournaments/my-registrations/
    """
    serializer_class = TournamentRegistrationSerializer
    permission_classes = [IsPlayerUser]
    
    def get_queryset(self):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        return TournamentRegistration.objects.filter(player=player_profile)


class PlayerScrimRegistrationsView(generics.ListAPIView):
    """
    Get all scrim registrations of a player
    GET /api/tournaments/scrims/my-registrations/
    """
    serializer_class = ScrimRegistrationSerializer
    permission_classes = [IsPlayerUser]
    
    def get_queryset(self):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        return ScrimRegistration.objects.filter(player=player_profile)


# ============= Host Rating Views =============

class HostRatingCreateView(generics.CreateAPIView):
    """
    Player rates a host
    POST /api/tournaments/host/<host_id>/rate/
    """
    serializer_class = HostRatingSerializer
    permission_classes = [IsPlayerUser]
    
    def perform_create(self, serializer):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        host_id = self.kwargs['host_id']
        host_profile = HostProfile.objects.get(id=host_id)
        
        serializer.save(player=player_profile, host=host_profile)


class HostRatingsListView(generics.ListAPIView):
    """
    Get all ratings for a host
    GET /api/tournaments/host/<host_id>/ratings/
    """
    serializer_class = HostRatingSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        host_id = self.kwargs['host_id']
        return HostRating.objects.filter(host_id=host_id)

