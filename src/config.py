from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    technician_password: str = os.getenv("TECHNICIAN_PASSWORD", "")
    coordinator_password: str = os.getenv("COORDINATOR_PASSWORD", "")
    db_path: Path = ROOT / os.getenv("DB_PATH", "data/runtime/technician_scheduling.db")
    intake_backend: str = os.getenv("INTAKE_BACKEND", "mock")
    llm_backend: str = os.getenv("LLM_BACKEND", os.getenv("INTAKE_BACKEND", "mock"))
    aws_region: str = os.getenv("AWS_REGION", "ap-southeast-1")
    bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "")
    local_llm_base_url: str = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    local_llm_api_key: str = os.getenv("LOCAL_LLM_API_KEY", "local")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "")
    local_llm_timeout_sec: int = int(os.getenv("LOCAL_LLM_TIMEOUT_SEC", "60"))
    slot_granularity_min: int = int(os.getenv("SLOT_GRANULARITY_MIN", "30"))


settings = Settings()
