from .config import (
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
                play_url TEXT,
                video_url TEXT,
                image_url TEXT,
                prediction_bot_link TEXT,
                bot_role VARCHAR(32) NOT NULL DEFAULT 'private',
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                video_file_id TEXT,
                image_file_id TEXT,
                deposit_file_id TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        # 兼容旧表：若缺少 play_url 列则补充
        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'bots' AND COLUMN_NAME = 'play_url'
                """,
                (MYSQL_DATABASE,)
            )
            count = cursor.fetchone()[0]
            if count == 0:
                cursor.execute("ALTER TABLE bots ADD COLUMN play_url TEXT")
        except Exception:
            pass
        # 兼容旧表：若缺少 bot_role 列则补充
        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'bots' AND COLUMN_NAME = 'bot_role'
                """,
                (MYSQL_DATABASE,)
            )
            count = cursor.fetchone()[0]
            if count == 0:
                cursor.execute("ALTER TABLE bots ADD COLUMN bot_role VARCHAR(32) NOT NULL DEFAULT 'private'")
        except Exception:
            pass
    else:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                bot_token TEXT NOT NULL UNIQUE,
                registration_link TEXT NOT NULL,
                channel_link TEXT,
                play_url TEXT,
                video_url TEXT,
                image_url TEXT,
                prediction_bot_link TEXT,
                bot_role TEXT NOT NULL DEFAULT 'private',
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
        for col in ("video_file_id", "image_file_id", "deposit_file_id", "play_url", "bot_role"):
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE bots ADD COLUMN {col} TEXT")

    conn.commit()
    conn.close()
    print("数据库初始化完成。")


def get_active_bots(role: str | None = None):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                if role:
                    cursor.execute("SELECT * FROM bots WHERE is_active = 1 AND bot_role = %s", (role,))
                    return cursor.fetchall()
                else:
                    cursor.execute("SELECT * FROM bots WHERE is_active = 1")
                    return cursor.fetchall()
        else:
            cursor = conn.cursor()
            if role:
                cursor.execute("SELECT * FROM bots WHERE is_active = 1 AND bot_role = ?", (role,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            else:
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


def add_bot(agent_name: str, token: str, reg_link: str, channel_link: str = None, play_url: str | None = None, video_url: str = None, image_url: str = None, prediction_bot_link: str = None, bot_role: str = 'private'):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            try:
                with conn.cursor() as cursor:
                    sql = (
                        "INSERT INTO bots (agent_name, bot_token, registration_link, channel_link, play_url, video_url, image_url, prediction_bot_link, bot_role) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    )
                    cursor.execute(sql, (agent_name, token, reg_link, channel_link, play_url, video_url, image_url, prediction_bot_link, bot_role))
                    conn.commit()
                    bot_id = cursor.lastrowid
                    return get_bot_by_id(bot_id)
            except Exception:
                return None
        else:
            cursor = conn.cursor()
            sql = (
                "INSERT INTO bots (agent_name, bot_token, registration_link, channel_link, play_url, video_url, image_url, prediction_bot_link, bot_role) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            cursor.execute(sql, (agent_name, token, reg_link, channel_link, play_url, video_url, image_url, prediction_bot_link, bot_role))
            conn.commit()
            bot_id = cursor.lastrowid
            return get_bot_by_id(bot_id)
    finally:
        conn.close()


def update_bot_file_ids(
    token: str,
    video_file_id: str | None = None,
    image_file_id: str | None = None,
    deposit_file_id: str | None = None,
    sticker_file_id: str | None = None,
    first_image_file_id: str | None = None,
):
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
        if sticker_file_id is not None:
            fields.append("sticker_file_id = %s" if DB_BACKEND == "mysql" else "sticker_file_id = ?")
            values.append(sticker_file_id)
        if first_image_file_id is not None:
            fields.append("first_image_file_id = %s" if DB_BACKEND == "mysql" else "first_image_file_id = ?")
            values.append(first_image_file_id)
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


def delete_bot_by_id(bot_id: int) -> bool:
    """按 id 删除机器人，并尝试清理其 users 关联（通过 token）"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                # 先取 token 以便清理 users
                cursor.execute("SELECT bot_token FROM bots WHERE id = %s", (bot_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                token = row["bot_token"] if isinstance(row, dict) else row[0]

                cursor.execute("DELETE FROM bots WHERE id = %s", (bot_id,))
                if cursor.rowcount == 0:
                    return False
                try:
                    cursor.execute("DELETE FROM users WHERE bot_token = %s", (token,))
                except Exception:
                    pass
                conn.commit()
                return True
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT bot_token FROM bots WHERE id = ?", (bot_id,))
            row = cursor.fetchone()
            if not row:
                return False
            token = row[0] if not isinstance(row, sqlite3.Row) else row["bot_token"]

            cursor.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
            if cursor.rowcount == 0:
                return False
            try:
                cursor.execute("DELETE FROM users WHERE bot_token = ?", (token,))
            except Exception:
                pass
            conn.commit()
            return True
    except Exception as e:
        print(f"按ID删除机器人时出错: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
