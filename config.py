"""
Mind OS 配置模块
优先从环境变量/.env 文件加载配置
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件（生产环境通常直接用环境变量）
load_dotenv()

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-46fb9b43b9a14b61958550d63bd08a35")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-reasoner")

# 服务器配置
# Render/Vercel 会自动注入 PORT 环境变量
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("PORT", os.getenv("FLASK_PORT", 5555)))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# 数据存储
DATA_FILE = os.getenv("DATA_FILE", "memory.json")
