import sqlite3
import os
from config import DB_FILE  # 从config导入DB_FILE


def get_db_connection():
    """建立并返回数据库连接"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    """初始化数据库，创建表结构"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bots';")
    if not cursor.fetchone():
        # --- 关键修改：增加 image_file_id 和 prediction_bot_link ---
        cursor.execute("""
                       CREATE TABLE bots
                       (
                           id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name          TEXT    NOT NULL,
                           bot_token           TEXT    NOT NULL UNIQUE,
                           registration_link   TEXT    NOT NULL,
                           channel_link        TEXT,
                           video_url           TEXT,
                           image_url           TEXT,
                           prediction_bot_link TEXT,
                           is_active           BOOLEAN NOT NULL DEFAULT 1
                       );
                       """)
        print("表 'bots' 创建完成。")

    # ... users 表的创建逻辑不变 ...
    conn.commit()
    conn.close()
    print("数据库初始化完成。")


def get_active_bots():
    conn = get_db_connection()
    bots = conn.execute("SELECT * FROM bots WHERE is_active = 1").fetchall()
    conn.close()
    return [dict(bot) for bot in bots]


def get_all_bots():
    conn = get_db_connection()
    bots = conn.execute("SELECT * FROM bots").fetchall()
    conn.close()
    return [dict(bot) for bot in bots]


def add_bot(agent_name: str, token: str, reg_link: str, channel_link: str = None, video_url: str = None, image_url: str = None, prediction_bot_link: str = None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bots (agent_name, bot_token, registration_link, channel_link, video_url, image_url, prediction_bot_link) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agent_name, token, reg_link, channel_link, video_url, image_url, prediction_bot_link)
        )
        conn.commit()
        bot_id = cursor.lastrowid
        return get_bot_by_id(bot_id)
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def toggle_bot_status(token: str):
    conn = get_db_connection()
    # 先获取当前状态
    current_status = conn.execute("SELECT is_active FROM bots WHERE bot_token = ?", (token,)).fetchone()
    if not current_status:
        return None

    # 切换状态
    new_status = not current_status['is_active']
    conn.execute("UPDATE bots SET is_active = ? WHERE bot_token = ?", (new_status, token))
    conn.commit()
    conn.close()
    return new_status


def get_bot_by_token(token: str):
    conn = get_db_connection()
    bot = conn.execute("SELECT * FROM bots WHERE bot_token = ?", (token,)).fetchone()
    conn.close()
    return dict(bot) if bot else None


def get_bot_by_id(bot_id: int):
    conn = get_db_connection()
    bot = conn.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
    conn.close()
    return dict(bot) if bot else None


def delete_bot(token: str) -> bool:
    """从数据库中删除一个机器人及其所有关联的用户数据"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. 从 bots 表中删除机器人
        cursor.execute("DELETE FROM bots WHERE bot_token = ?", (token,))
        if cursor.rowcount == 0:
            # 如果没有找到匹配的机器人，说明删除失败
            conn.close()
            return False

        # 2. 从 users 表中删除该机器人的所有用户记录
        cursor.execute("DELETE FROM users WHERE bot_token = ?", (token,))

        conn.commit()
        return True
    except Exception as e:
        print(f"删除机器人时出错: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
