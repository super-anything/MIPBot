import os
from dotenv import load_dotenv

load_dotenv()

# --- 代理机器人数据库 ---
DB_FILE = "bots.db"

# Which DB backend to use: 'sqlite' (default for local) or 'mysql' (production)
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()

# --- Cloud SQL MySQL settings ---
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "bots")

# --- 主管理机器人配置 ---
# 在 .env 文件中添加这一行: ADMIN_BOT_TOKEN="YOUR_ADMIN_BOT_TOKEN_HERE"
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

# --- 授权管理员列表 ---
# 将你和运营团队成员的Telegram User ID加到这里（必须是数字）
# 示例: ADMIN_USER_IDS = [12345678, 98765432]
ADMIN_USER_IDS = [
    8082148171,8064152515,6425667576 # 替换成你的 User ID
]


IMAGE_LIBRARY = {
    'find_id': [
        "https://storage.googleapis.com/axibot/dan/login.jpg"  # 引导图链接
    ],
    'deposit_guide': [
        "https://storage.googleapis.com/axibot/fbot/depodit2.mp4"  # 引导视频链接
    ],
    'firstpng': [
        "https://storage.googleapis.com/axibot/fbot/firstpng.jpg"  # 引导图链接
    ]
}

if not ADMIN_BOT_TOKEN:
    raise ValueError("请在 .env 文件中设置你的 ADMIN_BOT_TOKEN")

if not ADMIN_USER_IDS:
    raise ValueError("请在 config.py 中设置 ADMIN_USER_IDS 列表")
