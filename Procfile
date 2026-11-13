
web: gunicorn bookmyseat.wsgi:application
worker: celery -A bookmyseat worker --loglevel=info --pool=solo --concurrency=1
