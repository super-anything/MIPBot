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
    6425667576,
    7793379142,
    7342278579,
    7089692292,
    7876956365,
    8160955663,
    8289551218,
    8232719472,
    8444055438,
    6815101080,
    6464328931,
    8239249973,
    7636953099,
    7572097367,
    8409565237,
    8220057586,
    7606345268,
    6916001522,
    8006222013,
    7590272970

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
