from config import (
    DB_BACKEND,
    DB_FILE,
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
)

if DB_BACKEND == "mysql":
    import pymysql
    from pymysql.cursors import DictCursor
else:
    import sqlite3


def get_db_connection():
    """建立并返回数据库连接，支持 sqlite 与 mysql"""
    if DB_BACKEND == "mysql":
        return pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            cursorclass=DictCursor,
            autocommit=False,
            charset="utf8mb4",
        )
    # sqlite (默认本地)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    """初始化数据库，创建表结构（支持 MySQL / SQLite）"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if DB_BACKEND == "mysql":
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
    else:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                bot_token TEXT NOT NULL UNIQUE,
                registration_link TEXT NOT NULL,
                channel_link TEXT,
                video_url TEXT,
                image_url TEXT,
                prediction_bot_link TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                video_file_id TEXT,
                image_file_id TEXT,
                deposit_file_id TEXT
            );
            """
        )
        # 兼容旧表：为缺失的列做补充
        cursor.execute("PRAGMA table_info('bots');")
        existing_cols = {row[1] for row in cursor.fetchall()}
        for col in ("video_file_id", "image_file_id", "deposit_file_id"):
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE bots ADD COLUMN {col} TEXT")

    conn.commit()
    conn.close()
    print("数据库初始化完成。")


def get_active_bots():
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM bots WHERE is_active = 1")
                return cursor.fetchall()
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bots WHERE is_active = 1")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def get_all_bots():
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM bots")
                return cursor.fetchall()
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bots")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def add_bot(agent_name: str, token: str, reg_link: str, channel_link: str = None, video_url: str = None, image_url: str = None, prediction_bot_link: str = None):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            try:
                with conn.cursor() as cursor:
                    sql = (
                        "INSERT INTO bots (agent_name, bot_token, registration_link, channel_link, video_url, image_url, prediction_bot_link) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    )
                    cursor.execute(sql, (agent_name, token, reg_link, channel_link, video_url, image_url, prediction_bot_link))
                    conn.commit()
                    bot_id = cursor.lastrowid
                    return get_bot_by_id(bot_id)
            except Exception:
                return None
        else:
            cursor = conn.cursor()
            sql = (
                "INSERT INTO bots (agent_name, bot_token, registration_link, channel_link, video_url, image_url, prediction_bot_link) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            )
            cursor.execute(sql, (agent_name, token, reg_link, channel_link, video_url, image_url, prediction_bot_link))
            conn.commit()
            bot_id = cursor.lastrowid
            return get_bot_by_id(bot_id)
    finally:
        conn.close()


def update_bot_file_ids(token: str, video_file_id: str | None = None, image_file_id: str | None = None, deposit_file_id: str | None = None):
    """按需更新某个机器人的媒体 file_id 字段。不会覆盖为 None 的字段。"""
    conn = get_db_connection()
    try:
        fields = []
        values = []
        if video_file_id is not None:
            fields.append("video_file_id = %s" if DB_BACKEND == "mysql" else "video_file_id = ?")
            values.append(video_file_id)
        if image_file_id is not None:
            fields.append("image_file_id = %s" if DB_BACKEND == "mysql" else "image_file_id = ?")
            values.append(image_file_id)
        if deposit_file_id is not None:
            fields.append("deposit_file_id = %s" if DB_BACKEND == "mysql" else "deposit_file_id = ?")
            values.append(deposit_file_id)
        if not fields:
            return False
        values.append(token)
        if DB_BACKEND == "mysql":
            sql = f"UPDATE bots SET {', '.join(fields)} WHERE bot_token = %s"
            with conn.cursor() as cur:
                cur.execute(sql, tuple(values))
                conn.commit()
                return cur.rowcount > 0
        else:
            sql = f"UPDATE bots SET {', '.join(fields)} WHERE bot_token = ?"
            cur = conn.cursor()
            cur.execute(sql, tuple(values))
            conn.commit()
            return cur.rowcount > 0
    finally:
        conn.close()

def toggle_bot_status(token: str):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("SELECT is_active FROM bots WHERE bot_token = %s", (token,))
                current = cursor.fetchone()
                if not current:
                    return None
                new_status = 0 if current["is_active"] else 1
                cursor.execute("UPDATE bots SET is_active = %s WHERE bot_token = %s", (new_status, token))
                conn.commit()
                return bool(new_status)
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM bots WHERE bot_token = ?", (token,))
            row = cursor.fetchone()
            if not row:
                return None
            current_active = row["is_active"]
            new_status = 0 if current_active else 1
            cursor.execute("UPDATE bots SET is_active = ? WHERE bot_token = ?", (new_status, token))
            conn.commit()
            return bool(new_status)
    finally:
        conn.close()


def get_bot_by_token(token: str):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM bots WHERE bot_token = %s", (token,))
                bot = cursor.fetchone()
                return bot if bot else None
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bots WHERE bot_token = ?", (token,))
            row = cursor.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def get_bot_by_id(bot_id: int):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM bots WHERE id = %s", (bot_id,))
                bot = cursor.fetchone()
                return bot if bot else None
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bots WHERE id = ?", (bot_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def delete_bot(token: str) -> bool:
    """从数据库中删除一个机器人及其所有关联的用户数据"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM bots WHERE bot_token = %s", (token,))
                if cursor.rowcount == 0:
                    return False
                cursor.execute("DELETE FROM users WHERE bot_token = %s", (token,))
                conn.commit()
                return True
        else:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bots WHERE bot_token = ?", (token,))
            if cursor.rowcount == 0:
                return False
            # 若 users 表存在则尝试删除关联记录（忽略失败）
            try:
                cursor.execute("DELETE FROM users WHERE bot_token = ?", (token,))
            except Exception:
                pass
            conn.commit()
            return True
    except Exception as e:
        print(f"删除机器人时出错: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
