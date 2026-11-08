import os
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "data/edge.db"))
MODEL_DIR = Path(os.getenv("MODEL_DIR", "models"))
API_TOKEN = os.getenv("API_TOKEN", "")
CLOUD_URL = os.getenv("CLOUD_URL", "").rstrip("/")
CLOUD_TOKEN = os.getenv("CLOUD_API_TOKEN", "")
NODE_ROLE = os.getenv("NODE_ROLE", "edge")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3:4b")
