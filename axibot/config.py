import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("SIGNAL_BOT_TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")

if not BOT_TOKEN or not TARGET_CHAT_ID:
    raise ValueError("请在 .env 文件中正确设置 SIGNAL_BOT_TOKEN 和 TARGET_CHAT_ID")
