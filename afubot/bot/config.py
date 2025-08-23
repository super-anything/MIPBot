import os
from dotenv import load_dotenv

load_dotenv()

# --- 代理机器人数据库 ---
DB_FILE = "bots.db"

# --- 主管理机器人配置 ---
# 在 .env 文件中添加这一行: ADMIN_BOT_TOKEN="YOUR_ADMIN_BOT_TOKEN_HERE"
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

# --- 授权管理员列表 ---
# 将你和运营团队成员的Telegram User ID加到这里（必须是数字）
# 示例: ADMIN_USER_IDS = [12345678, 98765432]
ADMIN_USER_IDS = [
    8082148171,8064152515 # 替换成你的 User ID
]

REGISTRATION_LINK = [
        "www.baidu.com"#注册链接
    ]

IMAGE_LIBRARY = {
    'find_id': [
        "https://storage.googleapis.com/axibot/dan/login.jpg"  # 引导图链接
    ],
    'deposit_guide': [
        "https://storage.googleapis.com/axibot/fbot/deposti.mp4"  # 引导视频链接
    ]
}

if not ADMIN_BOT_TOKEN:
    raise ValueError("请在 .env 文件中设置你的 ADMIN_BOT_TOKEN")

if not ADMIN_USER_IDS:
    raise ValueError("请在 config.py 中设置 ADMIN_USER_IDS 列表")
