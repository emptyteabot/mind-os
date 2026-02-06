import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-46fb9b43b9a14b61958550d63bd08a35")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-reasoner")
AGENT_MODEL = os.getenv("AGENT_MODEL", "deepseek-chat")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("PORT", os.getenv("FLASK_PORT", 5555)))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
DATA_FILE = os.getenv("DATA_FILE", "memory.json")
