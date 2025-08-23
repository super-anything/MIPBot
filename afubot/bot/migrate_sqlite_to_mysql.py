import os
import sys
from typing import Any, Dict

from dotenv import load_dotenv

# Ensure we load same config as the bot
load_dotenv()

from config import (
    DB_FILE,
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
)

import sqlite3
import pymysql
from pymysql.cursors import DictCursor


def read_all_bots_from_sqlite(sqlite_path: str) -> list[Dict[str, Any]]:
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        # best-effort: if table not exists, raise
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bots';")
        if not cur.fetchone():
            raise RuntimeError("Table 'bots' not found in SQLite database")
        cur.execute("SELECT * FROM bots")
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def ensure_mysql_table(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bots (
                id INT PRIMARY KEY AUTO_INCREMENT,
                agent_name VARCHAR(255) NOT NULL,
                bot_token VARCHAR(255) NOT NULL UNIQUE,
                registration_link TEXT NOT NULL,
                channel_link TEXT,
                video_url TEXT,
                image_url TEXT,
                prediction_bot_link TEXT,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                video_file_id TEXT,
                image_file_id TEXT,
                deposit_file_id TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
    conn.commit()


def upsert_bots_to_mysql(conn, bots: list[Dict[str, Any]]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    with conn.cursor() as cursor:
        for bot in bots:
            # normalize keys possibly missing in old sqlite
            agent_name = bot.get("agent_name")
            bot_token = bot.get("bot_token")
            registration_link = bot.get("registration_link")
            channel_link = bot.get("channel_link")
            video_url = bot.get("video_url")
            image_url = bot.get("image_url")
            prediction_bot_link = bot.get("prediction_bot_link")
            is_active = bot.get("is_active", 1)
            video_file_id = bot.get("video_file_id")
            image_file_id = bot.get("image_file_id")
            deposit_file_id = bot.get("deposit_file_id")

            # try insert, if duplicate, then update
            try:
                cursor.execute(
                    (
                        "INSERT INTO bots (agent_name, bot_token, registration_link, channel_link, video_url, image_url, prediction_bot_link, is_active, video_file_id, image_file_id, deposit_file_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    ),
                    (
                        agent_name,
                        bot_token,
                        registration_link,
                        channel_link,
                        video_url,
                        image_url,
                        prediction_bot_link,
                        is_active,
                        video_file_id,
                        image_file_id,
                        deposit_file_id,
                    ),
                )
                inserted += 1
            except pymysql.err.IntegrityError:
                cursor.execute(
                    (
                        "UPDATE bots SET agent_name=%s, registration_link=%s, channel_link=%s, video_url=%s, image_url=%s, prediction_bot_link=%s, is_active=%s, video_file_id=%s, image_file_id=%s, deposit_file_id=%s "
                        "WHERE bot_token=%s"
                    ),
                    (
                        agent_name,
                        registration_link,
                        channel_link,
                        video_url,
                        image_url,
                        prediction_bot_link,
                        is_active,
                        video_file_id,
                        image_file_id,
                        deposit_file_id,
                        bot_token,
                    ),
                )
                updated += 1
    conn.commit()
    return inserted, updated


def main():
    sqlite_path = DB_FILE

    print(f"Reading from SQLite: {sqlite_path}")
    bots = read_all_bots_from_sqlite(sqlite_path)
    print(f"Found {len(bots)} rows in SQLite 'bots'.")

    print("Connecting to MySQL...")
    mysql_conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=DictCursor,
        autocommit=False,
        charset="utf8mb4",
    )

    try:
        ensure_mysql_table(mysql_conn)
        inserted, updated = upsert_bots_to_mysql(mysql_conn, bots)
        print(f"Migration finished. Inserted: {inserted}, Updated: {updated}")
    finally:
        mysql_conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)
