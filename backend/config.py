import os
from dotenv import load_dotenv

load_dotenv()

APP_MODE = os.getenv("APP_MODE", "live").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/ai_observatory.db")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
EXPERIMENT_BUDGET_USD = float(os.getenv("EXPERIMENT_BUDGET_USD", "5"))
