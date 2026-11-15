FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/astrohealth-backend
COPY astrohealth-backend/pyproject.toml ./
COPY astrohealth-backend/app ./app
RUN pip install --no-cache-dir '.[encrypted]'
COPY astrohealth-backend/configs ./configs
COPY astrohealth-backend/migrations ./migrations
COPY astrohealth-backend/alembic.ini ./
COPY astrohealth-backend/models_registry ./models_registry
COPY dist /app/dist
RUN useradd --create-home astro && mkdir -p /data && chown astro:astro /data
USER astro
ENV ASTRO_DATA_DIR=/data
EXPOSE 8000
CMD ["sh","-c","alembic upgrade head && python -m app.cli serve"]
