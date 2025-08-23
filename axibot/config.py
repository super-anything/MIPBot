import os
from dotenv import load_dotenv

load_dotenv()

# --- 基础配置 ---
BOT_TOKEN = os.getenv("SIGNAL_BOT_TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID") # 用于发送带单信号的频道ID

# --- 对话流程中使用的固定链接 ---
# 您可以在这里修改对话中用到的链接
REGISTRATION_LINK = "http://www.example.com/register"
CHANNEL_LINK = "http://t.me/your_channel_link"
PREDICTION_BOT_LINK = "http://t.me/your_prediction_bot_link"


# --- 分类图片库 (URL) ---
IMAGE_LIBRARY = {
    'registration': [
        "https://i.imgur.com/example-reg1.jpg",
        "https://i.imgur.com/example-reg2.png",
    ],
    'deposit': [
        "https://i.imgur.com/example-recharge1.jpg",
        "https://i.imgur.com/example-recharge2.gif",
    ],
    'firstdd': ["https://storage.googleapis.com/axibot/axidaidan1.jpg"
    ]
}

if not BOT_TOKEN or not TARGET_CHAT_ID:
    raise ValueError("请在 .env 文件中正确设置 SIGNAL_BOT_TOKEN 和 TARGET_CHAT_ID")
