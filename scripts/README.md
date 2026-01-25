# Test Data Generation Scripts

## Create Test Tournaments Script

### Overview
This script creates comprehensive test data for tournaments and scrims to test all UI scenarios.

### What it creates:
- **54 total events** (27 tournaments + 27 scrims)
- **3 plan types**: Basic, Featured, Premium
- **3 status types**: Upcoming, Ongoing, Completed
- **3 registration states** (for upcoming): Not Started, Open, Ended

### How to run:

#### Method 1: Using Django shell
```bash
cd scrimverse-backend
python manage.py shell < scripts/create_test_tournaments.py
```

#### Method 2: Direct execution
```bash
cd scrimverse-backend
python scripts/create_test_tournaments.py
```

### What you can test after running:

#### Tournaments Page (`/tournaments`)
- **Upcoming Tab**:
  - "Registration Starts Soon" badge (for events where registration hasn't started)
  - "Register Now" button (for events with open registration)
  - "Registration Ended" badge (for events where registration closed)

- **Active Tab**:
  - Live tournaments with pulsing red badge
  - View Details button only

- **Past Tab**:
  - Completed tournaments with checkmark badge
  - View Details + Points Table buttons

#### Scrims Page (`/scrims`)
- Same scenarios as tournaments but for SCRIM event mode

#### Badge Testing:
- **Status Badges** (Top Left):
  - 🕐 UPCOMING (purple with clock icon)
  - 🔴 LIVE (red pulsing with dot icon)
  - ✓ COMPLETED (gray with checkmark icon)

- **Plan Type Badges** (Top Right):
  - ⭐ BASIC (blue with star outline)
  - ⭐ FEATURED (green pulsing with filled star)
  - 💎 PREMIUM (gold pulsing with diamond icon)

#### Sorting:
- Verify Premium listings appear first
- Then Featured listings
- Then Basic listings

### Test Host Credentials:
- **Username**: testhost
- **Email**: testhost@scrimverse.com
- **Password**: testpass123

### Cleanup:
The script automatically deletes old test data from the test host before creating new data.

### Notes:
- The script uses realistic time calculations for registration windows
- All tournaments have proper rounds configured
- Scrims are limited to 25 teams, tournaments to 100 teams
- Prize pools and entry fees vary by plan type
