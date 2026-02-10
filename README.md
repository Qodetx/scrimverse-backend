Scrimverse Backend

A comprehensive Django REST API backend for managing esports tournaments, scrims, team registrations, payments, and user authentication.

🎯 Overview

Scrimverse Backend is a robust Django-based REST API that powers the Scrimverse platform. It provides complete tournament management, user authentication, payment processing, real-time notifications, and administrative controls for esports competitions.

✨ Key Features


🏆 Tournament & Scrim Management



Tournament System: Multi-round, multi-group tournament management with qualification rounds

Scrim Mode: Quick practice matches with simplified rules (1 round, max 25 teams, max 6 matches)

Match Management: Create, update, and track match results with detailed statistics

Group & Round Management: Flexible group creation and round progression

Leaderboards: Real-time standings and points tracking

Winner Selection: Automated winner determination based on points


👥 User & Team Management



User Roles: Player and Host accounts with role-specific permissions

Team System: Create teams, manage rosters, handle join requests

Host Verification: Admin approval workflow for tournament hosts

Profile Management: Comprehensive user and team profiles with statistics


🔐 Authentication & Security



JWT Authentication: Secure token-based authentication

Google OAuth: Social login integration

Email Verification: Email-based account verification

Password Reset: Secure password recovery flow

Role-based Permissions: Granular access control


💳 Payment Integration



PhonePe Gateway: Integrated payment processing for tournament registrations

Pricing Plans: Basic (₹299), Featured (₹499), Premium (₹799) tiers

Payment Tracking: Complete payment history and status tracking

Refund Support: Payment refund capabilities


📧 Email & Notifications



AWS SES Integration: Reliable email delivery

Celery Tasks: Asynchronous email sending

Email Templates: Professional HTML email templates

Notification System: Tournament updates, match results, and announcements


🎨 Media & Storage



AWS S3 Integration: Cloud storage for banners, profile images, and documents

Local Storage: Development mode file storage

Image Processing: Automatic image optimization

Default Assets: Game-specific default banners


⚡ Performance & Caching



Redis Caching: High-performance data caching

Query Optimization: Efficient database queries with select_related/prefetch_related

Background Tasks: Celery-based async task processing


🛠️ Tech Stack



Framework: Django 5.0.0

API: Django REST Framework 3.14.0

Database: PostgreSQL (production) / SQLite (development)

Authentication: JWT (djangorestframework-simplejwt)

Task Queue: Celery 5.3.4

Cache: Redis 5.0.1

Storage: AWS S3 (boto3, django-storages)

Email: AWS SES

Payment: PhonePe Payment Gateway

OAuth: Google OAuth 2.0


📋 Prerequisites


Python 3.10 or higher
PostgreSQL 13+ (for production) or SQLite (for development)
Redis 6.0+
pip (Python package manager)
Virtual environment tool (venv or virtualenv)


🚀 Local Setup

1. Clone the Repository


git clone https://gitlab.com/sukruth1/scrimverse-backend.git
cd scrimverse-backend


2. Create Virtual Environment


python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate


3. Install Dependencies


pip install -r requirements.txt


4. Environment Configuration

Create a .env file in the project root:

# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Settings (SQLite for development)
DB_NAME=scrimverse
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432

# Redis Settings
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_CACHE_TTL=300

# JWT Settings
JWT_SECRET_KEY=your-jwt-secret-key
ACCESS_TOKEN_LIFETIME_MINUTES=60
REFRESH_TOKEN_LIFETIME_DAYS=7

# CORS Settings
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Google OAuth Settings
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# AWS S3 Settings (optional for local development)
USE_S3=False
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=ap-south-1

# PhonePe Payment Gateway
CLIENT_ID=your-phonepe-client-id
CLIENT_VERSION=1
CLIENT_SECRET=your-phonepe-client-secret
PHONEPE_ENV=SANDBOX
PHONEPE_CALLBACK_USERNAME=your-callback-username
PHONEPE_CALLBACK_PASSWORD=your-callback-password

# Email Configuration (AWS SES)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=email-smtp.ap-south-1.amazonaws.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-ses-smtp-username
EMAIL_HOST_PASSWORD=your-ses-smtp-password
DEFAULT_FROM_EMAIL=hello@scrimverse.com
SUPPORT_EMAIL=support@scrimverse.com
ADMIN_EMAIL=admin@scrimverse.com


5. Database Setup


# Run migrations
python manage.py migrate

# Create superuser for admin access
python manage.py createsuperuser


6. Start Redis Server


# On macOS (using Homebrew)
brew services start redis

# On Linux
sudo systemctl start redis

# Verify Redis is running
redis-cli ping  # Should return "PONG"


7. Start Celery Worker (in a new terminal)


source .venv/bin/activate
celery -A scrimverse worker --loglevel=info


8. Start Celery Beat (in another new terminal)


source .venv/bin/activate
celery -A scrimverse beat --loglevel=info


9. Start Django Development Server


python manage.py runserver


The API will be available at http://localhost:8000/api/
10. Access Admin Panel

Navigate to http://localhost:8000/admin/ and login with your superuser credentials.

📁 Project Structure


scrimverse-backend/
├── accounts/              # User authentication & profiles
│   ├── models.py         # User, Profile, Team models
│   ├── views.py          # Auth endpoints
│   ├── serializers.py    # User serializers
│   ├── admin.py          # Admin customizations
│   └── tasks.py          # Email tasks
├── tournaments/           # Tournament & scrim management
│   ├── models.py         # Tournament, Match, Group models
│   ├── views.py          # Tournament endpoints
│   ├── groups_views.py   # Group management
│   ├── serializers.py    # Tournament serializers
│   ├── tasks.py          # Background tasks
│   └── services.py       # Business logic
├── payments/              # Payment processing
│   ├── models.py         # Payment, Transaction models
│   ├── views.py          # Payment endpoints
│   ├── services.py       # PhonePe integration
│   └── serializers.py    # Payment serializers
├── scrimverse/            # Project configuration
│   ├── settings.py       # Django settings
│   ├── urls.py           # URL routing
│   ├── celery.py         # Celery configuration
│   └── email_utils.py    # Email utilities
├── templates/             # Email templates
├── media/                 # Uploaded files (local)
├── scripts/               # Utility scripts
├── tests/                 # Test suite
├── manage.py              # Django management script
└── requirements.txt       # Python dependencies



🔌 API Endpoints

Authentication



POST /api/accounts/register/ - User registration

POST /api/accounts/login/ - User login

POST /api/accounts/token/refresh/ - Refresh JWT token

POST /api/accounts/google-auth/ - Google OAuth login

POST /api/accounts/verify-email/ - Email verification

POST /api/accounts/password-reset/ - Password reset request

POST /api/accounts/password-reset-confirm/ - Password reset confirmation

User & Team Management



GET /api/accounts/profile/ - Get user profile

PUT /api/accounts/profile/ - Update user profile

POST /api/accounts/teams/ - Create team

GET /api/accounts/teams/ - List user teams

POST /api/accounts/teams/{id}/join-request/ - Request to join team

GET /api/accounts/leaderboard/ - Global leaderboard

Tournaments



GET /api/tournaments/ - List tournaments

POST /api/tournaments/ - Create tournament (Host only)

GET /api/tournaments/{id}/ - Tournament details

PUT /api/tournaments/{id}/ - Update tournament (Host only)

POST /api/tournaments/{id}/register/ - Register for tournament

POST /api/tournaments/{id}/start/ - Start tournament (Host only)

GET /api/tournaments/{id}/standings/ - Tournament standings

POST /api/tournaments/{id}/select-winner/ - Select winner (Host only)

Scrims



GET /api/scrims/ - List scrims

POST /api/scrims/ - Create scrim (Host only)

GET /api/scrims/{id}/ - Scrim details

POST /api/scrims/{id}/register/ - Register for scrim

Matches & Groups



GET /api/tournaments/{id}/matches/ - List matches

POST /api/tournaments/{id}/matches/ - Create match (Host only)

PUT /api/matches/{id}/ - Update match results (Host only)

GET /api/tournaments/{id}/groups/ - List groups

POST /api/tournaments/{id}/groups/ - Create group (Host only)

Payments



POST /api/payments/initiate/ - Initiate payment

POST /api/payments/callback/ - Payment callback (PhonePe)

GET /api/payments/status/{transaction_id}/ - Check payment status

GET /api/payments/history/ - Payment history

Admin



GET /api/admin/stats/ - Platform statistics

GET /api/admin/users/ - User management

POST /api/admin/approve-host/{id}/ - Approve host verification


🧪 Testing


# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_tournaments.py

# Run tests in CI mode
pytest --cov --cov-report=xml --cov-report=term



🔧 Development Tools

Code Quality


# Format code with Black
black .

# Sort imports with isort
isort .

# Lint with flake8
flake8 .

# Security check with Bandit
bandit -r .

# Run all pre-commit hooks
pre-commit run --all-files


Database Management


# Create new migration
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Reset database (development only)
python manage.py flush

# Load sample data
python manage.py loaddata fixtures/sample_data.json


Utility Scripts


# Generate comprehensive test data
python scripts/generate_comprehensive_data.py

# Cleanup test accounts
python scripts/cleanup_test_accounts.py



🐳 Docker Support (Optional)


# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down



🌍 Deployment

Production Checklist


Set DEBUG=False in .env

Configure production database (PostgreSQL)
Set up AWS S3 for media storage (USE_S3=True)
Configure AWS SES for email
Set strong SECRET_KEY and JWT_SECRET_KEY

Update ALLOWED_HOSTS with production domain
Configure CORS for production frontend URL
Set up SSL/TLS certificates
Configure Redis for production
Set up Celery with supervisor or systemd
Use Gunicorn/uWSGI for WSGI server
Set up Nginx as reverse proxy

Environment Variables for Production

Ensure all sensitive credentials are properly set in production environment.

📊 Admin Portal Features

Access the Django admin at /admin/ to:


User Management: View, edit, and manage user accounts

Host Verification: Approve or reject host applications

Tournament Oversight: Monitor and manage all tournaments

Payment Tracking: View payment transactions and status

Team Management: Manage teams and rosters

Content Moderation: Review and moderate user-generated content

Analytics: View platform statistics and insights


🤝 Contributing


Fork the repository
Create a feature branch (git checkout -b feature/amazing-feature)
Commit your changes (git commit -m 'Add amazing feature')
Push to the branch (git push origin feature/amazing-feature)
Open a Merge Request


📝 License

This project is proprietary and confidential.

👥 Team



Development Team: Scrimverse Backend Team

Contact: support@scrimverse.com



🐛 Troubleshooting

Common Issues

Redis Connection Error

# Make sure Redis is running
redis-cli ping
# If not running, start Redis
brew services start redis  # macOS
sudo systemctl start redis  # Linux


Database Migration Issues

# Reset migrations (development only)
python manage.py migrate --fake-initial


Celery Not Processing Tasks

# Check Celery worker is running
celery -A scrimverse inspect active

# Restart Celery worker
pkill -f 'celery worker'
celery -A scrimverse worker --loglevel=info


Port Already in Use

# Kill process on port 8000
lsof -ti:8000 | xargs kill -9



📚 Additional Resources


Django Documentation
Django REST Framework
Celery Documentation
Redis Documentation
AWS S3 Documentation


Happy Coding! 🚀