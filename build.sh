#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Collect static files with whitenoise
python manage.py collectstatic --no-input

# Run database migrations (automatically loads all 109 food items, events, rooms, venues via migration 0023)
python manage.py migrate

# Seed updated event schedules and demo entries
python manage.py seed_demo
