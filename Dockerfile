FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Runs migrations before starting the app server every time the container
# boots -- safe to repeat (Django tracks applied migrations) and means a
# fresh deploy on a platform like Render never needs a separate manual
# migrate step. $PORT is read from the environment (PaaS platforms assign
# it dynamically); defaults to 8000 for docker-compose / local `docker run`.
CMD python manage.py migrate --noinput && \
    gunicorn census_tracker.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3
