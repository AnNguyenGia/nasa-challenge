FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
COPY ml/requirements.txt ml/requirements.txt
RUN pip install --no-cache-dir -r ml/requirements.txt     && useradd -u 10001 -m app && mkdir /models /tracking && chown app:app /models /tracking
COPY ml ./ml
USER app
ENV MODEL_DIR=/models
CMD ["python", "-m", "ml.train"]
