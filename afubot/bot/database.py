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
    else:
        # --- 迁移：为媒体 file_id 增加列（若不存在） ---
        cursor.execute("PRAGMA table_info('bots');")
        existing_cols = {row[1] for row in cursor.fetchall()}
        # 期望新增的列
        add_columns_sql = []
        if 'video_file_id' not in existing_cols:
            add_columns_sql.append("ALTER TABLE bots ADD COLUMN video_file_id TEXT")
        if 'image_file_id' not in existing_cols:
            add_columns_sql.append("ALTER TABLE bots ADD COLUMN image_file_id TEXT")
        if 'deposit_file_id' not in existing_cols:
            add_columns_sql.append("ALTER TABLE bots ADD COLUMN deposit_file_id TEXT")
        for sql in add_columns_sql:
            cursor.execute(sql)
        if add_columns_sql:
            print("已为 'bots' 表添加 file_id 字段：", ', '.join(stmt.split()[-2] for stmt in add_columns_sql))

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


def update_bot_file_ids(token: str, video_file_id: str | None = None, image_file_id: str | None = None, deposit_file_id: str | None = None):
    """按需更新某个机器人的媒体 file_id 字段。不会覆盖为 None 的字段。"""
    conn = get_db_connection()
    try:
        fields = []
        values = []
        if video_file_id is not None:
            fields.append("video_file_id = ?")
            values.append(video_file_id)
        if image_file_id is not None:
            fields.append("image_file_id = ?")
            values.append(image_file_id)
        if deposit_file_id is not None:
            fields.append("deposit_file_id = ?")
            values.append(deposit_file_id)
        if not fields:
            return False
        values.append(token)
        sql = f"UPDATE bots SET {', '.join(fields)} WHERE bot_token = ?"
        cur = conn.cursor()
        cur.execute(sql, tuple(values))
        conn.commit()
        return cur.rowcount > 0
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
