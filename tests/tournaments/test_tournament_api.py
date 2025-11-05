"""
Test cases for Tournament API (CRUD operations)
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from tournaments.models import Tournament
from datetime import timedelta
from django.utils import timezone
from tests.factories import TournamentFactory, HostProfileFactory, UserFactory


# Tournament List Tests

@pytest.mark.django_db
def test_list_tournaments_unauthenticated(api_client, multiple_tournaments):
    """Test listing tournaments without authentication"""
    response = api_client.get('/api/tournaments/')
    
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 3


@pytest.mark.django_db
def test_list_tournaments_authenticated(authenticated_client, multiple_tournaments):
    """Test listing tournaments with authentication"""
    response = authenticated_client.get('/api/tournaments/')
    
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 3


@pytest.mark.django_db
def test_filter_tournaments_by_status(api_client, multiple_tournaments):
    """Test filtering tournaments by status"""
    response = api_client.get('/api/tournaments/', {'status': 'upcoming'})
    
    assert response.status_code == status.HTTP_200_OK
    results = response.data.get('results', response.data)
    assert any(t['status'] == 'upcoming' for t in results)


@pytest.mark.django_db
def test_filter_tournaments_by_game(api_client):
    """Test filtering tournaments by game"""
    host_profile = HostProfileFactory()
    TournamentFactory(host=host_profile, game_name='BGMI')
    TournamentFactory(host=host_profile, game_name='Free Fire')
    
    response = api_client.get('/api/tournaments/', {'game': 'BGMI'})
    
    assert response.status_code == status.HTTP_200_OK
    results = response.data.get('results', response.data)
    assert len(results) == 1
    assert results[0]['game_name'] == 'BGMI'


@pytest.mark.django_db
def test_empty_tournament_list(api_client):
    """Test empty tournament list"""
    response = api_client.get('/api/tournaments/')
    
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 0


# Tournament Detail Tests

@pytest.mark.django_db
def test_get_tournament_detail(api_client, tournament):
    """Test getting tournament details"""
    response = api_client.get(f'/api/tournaments/{tournament.id}/')
    
    assert response.status_code == status.HTTP_200_OK
    assert response.data['id'] == tournament.id
    assert response.data['title'] == tournament.title
    assert 'host' in response.data


@pytest.mark.django_db
def test_get_nonexistent_tournament(api_client):
    """Test getting non-existent tournament"""
    response = api_client.get('/api/tournaments/99999/')
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


# Tournament Create Tests

@pytest.mark.django_db
def test_create_tournament_as_host(host_authenticated_client):
    """Test creating tournament as host"""
    now = timezone.now()
    data = {
        'title': 'New Tournament',
        'description': 'Test tournament description',
        'game_name': 'BGMI',
        'game_mode': 'Squad',
        'max_participants': 100,
        'entry_fee': '50.00',
        'prize_pool': '5000.00',
        'registration_start': now.isoformat(),
        'registration_end': (now + timedelta(days=5)).isoformat(),
        'tournament_start': (now + timedelta(days=6)).isoformat(),
        'tournament_end': (now + timedelta(days=6, hours=6)).isoformat(),
        'rules': 'Follow the rules'
    }
    response = host_authenticated_client.post('/api/tournaments/create/', data, format='json')
    
    assert response.status_code == status.HTTP_201_CREATED
    assert Tournament.objects.filter(title='New Tournament').exists()
    
    tournament = Tournament.objects.get(title='New Tournament')
    assert tournament.game_name == 'BGMI'
    assert tournament.max_participants == 100


@pytest.mark.django_db
def test_create_tournament_as_player_forbidden(authenticated_client):
    """Test creating tournament as player is forbidden"""
    data = {
        'title': 'Unauthorized Tournament',
        'game_name': 'BGMI',
    }
    response = authenticated_client.post('/api/tournaments/create/', data)
    
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_create_tournament_unauthenticated(api_client):
    """Test creating tournament without authentication"""
    data = {'title': 'Test'}
    response = api_client.post('/api/tournaments/create/', data)
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_create_tournament_missing_fields(host_authenticated_client):
    """Test creating tournament with missing required fields"""
    data = {
        'title': 'Incomplete Tournament'
    }
    response = host_authenticated_client.post('/api/tournaments/create/', data)
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# Tournament Update Tests

@pytest.mark.django_db
def test_update_own_tournament(host_authenticated_client, tournament):
    """Test host can update their own tournament"""
    data = {
        'title': 'Updated Tournament Title',
        'description': 'Updated description'
    }
    response = host_authenticated_client.patch(
        f'/api/tournaments/{tournament.id}/update/', 
        data,
        format='json'
    )
    
    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.title == 'Updated Tournament Title'


@pytest.mark.django_db
def test_update_other_host_tournament_forbidden(host_user):
    """Test host cannot update another host's tournament"""
    # Create another host
    other_host_user = UserFactory(user_type='host')
    other_host_profile = HostProfileFactory(user=other_host_user)
    tournament = TournamentFactory(host=other_host_profile)
    
    # Try to update with first host
    client = APIClient()
    client.force_authenticate(user=host_user)
    
    data = {'title': 'Hacked Title'}
    response = client.patch(f'/api/tournaments/{tournament.id}/update/', data)
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_update_tournament_as_player_forbidden(authenticated_client, tournament):
    """Test player cannot update tournament"""
    data = {'title': 'Player Update'}
    response = authenticated_client.patch(f'/api/tournaments/{tournament.id}/update/', data)
    
    assert response.status_code == status.HTTP_403_FORBIDDEN


# Tournament Delete Tests

@pytest.mark.django_db
def test_delete_own_tournament(host_authenticated_client, tournament):
    """Test host can delete their own tournament"""
    tournament_id = tournament.id
    response = host_authenticated_client.delete(f'/api/tournaments/{tournament_id}/delete/')
    
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Tournament.objects.filter(id=tournament_id).exists()


@pytest.mark.django_db
def test_delete_other_host_tournament_forbidden(host_user):
    """Test host cannot delete another host's tournament"""
    other_host_user = UserFactory(user_type='host')
    other_host_profile = HostProfileFactory(user=other_host_user)
    tournament = TournamentFactory(host=other_host_profile)
    
    client = APIClient()
    client.force_authenticate(user=host_user)
    
    response = client.delete(f'/api/tournaments/{tournament.id}/delete/')
    
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert Tournament.objects.filter(id=tournament.id).exists()


@pytest.mark.django_db
def test_delete_tournament_as_player_forbidden(authenticated_client, tournament):
    """Test player cannot delete tournament"""
    response = authenticated_client.delete(f'/api/tournaments/{tournament.id}/delete/')
    
    assert response.status_code == status.HTTP_403_FORBIDDEN


# Host Tournaments Tests

@pytest.mark.django_db
def test_get_host_tournaments(api_client, host_user, multiple_tournaments):
    """Test getting all tournaments by a specific host"""
    response = api_client.get(f'/api/tournaments/host/{host_user.host_profile.id}/')
    
    assert response.status_code == status.HTTP_200_OK
    results = response.data.get('results', response.data)
    assert len(results) == 3
    # Check host_name instead of nested host.id since it's a list serializer
    assert all('host_name' in t or 'host' in t for t in results)


@pytest.mark.django_db
def test_get_tournaments_for_nonexistent_host(api_client):
    """Test getting tournaments for non-existent host"""
    response = api_client.get('/api/tournaments/host/99999/')
    
    assert response.status_code == status.HTTP_200_OK
    # Response is paginated
    assert response.data['count'] == 0
    assert len(response.data['results']) == 0
