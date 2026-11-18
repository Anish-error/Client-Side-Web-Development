FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_SECRET_KEY=build-only-key-not-for-runtime python manage.py collectstatic --noinput

RUN addgroup --system ecoride && adduser --system --ingroup ecoride ecoride \
    && chown -R ecoride:ecoride /app
USER ecoride

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn ecoride.wsgi:application --bind 0.0.0.0:8000 --workers 3 --access-logfile -"]
