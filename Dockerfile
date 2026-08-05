# Minimal image for the Phase 2 web app. The CLI needs no dependencies at
# all and doesn't need a container; this is for `events web run`'s real
# production replacement (gunicorn via wsgi.py).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/events.db, config/profile.json, and data/flask_secret.key all live
# here — mount a persistent volume at this path or every deploy starts
# from a blank calendar. See README's "Deploying for real" section.
VOLUME ["/app/data"]

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "wsgi:app"]
