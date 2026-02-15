#!/usr/bin/env bash
# exit on error
set -o errexit

mkdir -p logs
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
