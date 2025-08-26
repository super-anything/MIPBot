import os
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(dotenv_path=PROJECT_ROOT / '.env')

# --- Database settings ---
DB_BACKEND = os.getenv('DB_BACKEND', 'sqlite').lower()
DB_FILE = str(PROJECT_ROOT / 'bots.db')

MYSQL_HOST = os.getenv('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3306'))
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'bots')

# --- Admin bot ---
ADMIN_BOT_TOKEN = os.getenv('ADMIN_BOT_TOKEN')

# Admin user ids
ADMIN_USER_IDS = [
    8082148171,
    8064152515,
    6425667576,#axi
    7793379142,#辉煌
    7342278579,#半仙
    7089692292,#axi
    7876956365,#
    8160955663,#姜维
    8289551218,#阿华
    8232719472,#莉莉
    8444055438,#千千
    6815101080,#小俊
    8239249973,#梦瑶
    7636953099,#富贵
    8409565237,#饭饭
    8220057586,#小雷
    7606345268,#阿平
    8006222013,#石榴
    7590272970,#阿夏
    6636614768,#阿浩
    7058607367,#成浩
    7004787520#阿南
]

# --- Media assets shared by both bots ---
IMAGE_LIBRARY = {
    'find_id': [
        "https://storage.googleapis.com/axibot/dan/login.jpg"
    ],
    'deposit_guide': [
        "https://storage.googleapis.com/axibot/fbot/depodit2.mp4"
    ],
    'firstpng': [
        "https://storage.googleapis.com/axibot/fbot/firstpng.jpg"
    ],
    'firstdd': [
        "https://storage.googleapis.com/axibot/axidaidan1.jpg"
    ]
}
