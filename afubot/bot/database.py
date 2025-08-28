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
                bot_role VARCHAR(32) NOT NULL DEFAULT 'private',
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                video_file_id TEXT,
                image_file_id TEXT,
                deposit_file_id TEXT,
                sticker_file_id TEXT,
                first_image_file_id TEXT,
                created_by BIGINT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        # --- 会话持久化表（用户私聊） ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_conversations (
                bot_token VARCHAR(255) NOT NULL,
                chat_id BIGINT NOT NULL,
                state VARCHAR(64) NOT NULL,
                payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (bot_token, chat_id)
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
        # 兼容旧表：补充缺失的新列
        for col, ddl in [
            ("sticker_file_id", "ALTER TABLE bots ADD COLUMN sticker_file_id TEXT"),
            ("first_image_file_id", "ALTER TABLE bots ADD COLUMN first_image_file_id TEXT"),
            ("created_by", "ALTER TABLE bots ADD COLUMN created_by BIGINT NULL"),
        ]:
            try:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'bots' AND COLUMN_NAME = %s
                    """,
                    (MYSQL_DATABASE, col)
                )
                if cursor.fetchone()[0] == 0:
                    cursor.execute(ddl)
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
                bot_role TEXT NOT NULL DEFAULT 'private',
                is_active INTEGER NOT NULL DEFAULT 1,
                video_file_id TEXT,
                image_file_id TEXT,
                deposit_file_id TEXT,
                sticker_file_id TEXT,
                first_image_file_id TEXT,
                created_by INTEGER
            );
            """
        )
        # 兼容旧表：为缺失的列做补充
        cursor.execute("PRAGMA table_info('bots');")
        existing_cols = {row[1] for row in cursor.fetchall()}
        for col in ("video_file_id", "image_file_id", "deposit_file_id", "play_url", "bot_role", "sticker_file_id", "first_image_file_id", "created_by"):
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE bots ADD COLUMN {col} TEXT")
        # 会话持久化表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_conversations (
                bot_token TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                state TEXT NOT NULL,
                payload_json TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (bot_token, chat_id)
            );
            """
        )

    conn.commit()
    conn.close()
    print("数据库初始化完成。")


# --- 用户会话持久化：CRUD ---
def get_user_conversation(bot_token: str, chat_id: int):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("SELECT state, payload_json FROM user_conversations WHERE bot_token=%s AND chat_id=%s", (bot_token, chat_id))
                row = cursor.fetchone()
                return dict(row) if row else None
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT state, payload_json FROM user_conversations WHERE bot_token=? AND chat_id=?", (bot_token, chat_id))
            row = cursor.fetchone()
            if row:
                return {"state": row[0], "payload_json": row[1]}
            return None
    finally:
        conn.close()


def upsert_user_conversation(bot_token: str, chat_id: int, state: str, payload_json: str | None = None):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO user_conversations (bot_token, chat_id, state, payload_json) VALUES (%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE state=VALUES(state), payload_json=VALUES(payload_json)",
                    (bot_token, chat_id, state, payload_json)
                )
                conn.commit()
        else:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO user_conversations (bot_token, chat_id, state, payload_json) VALUES (?,?,?,?) "
                "ON CONFLICT(bot_token, chat_id) DO UPDATE SET state=excluded.state, payload_json=excluded.payload_json",
                (bot_token, chat_id, state, payload_json)
            )
            conn.commit()
    finally:
        conn.close()


def delete_user_conversation(bot_token: str, chat_id: int):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM user_conversations WHERE bot_token=%s AND chat_id=%s", (bot_token, chat_id))
                conn.commit()
        else:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_conversations WHERE bot_token=? AND chat_id=?", (bot_token, chat_id))
            conn.commit()
    finally:
        conn.close()


def list_user_conversations(bot_token: str):
    """列出某个机器人的所有用户会话记录（用于重启后恢复流程）。"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT chat_id, state, payload_json FROM user_conversations WHERE bot_token=%s",
                    (bot_token,)
                )
                return cursor.fetchall()
        else:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT chat_id, state, payload_json FROM user_conversations WHERE bot_token=?",
                (bot_token,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


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


def add_bot(agent_name: str, token: str, reg_link: str, channel_link: str = None, play_url: str | None = None, video_url: str = None, image_url: str = None, bot_role: str = 'private', created_by: int | None = None):
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            try:
                with conn.cursor() as cursor:
                    sql = (
                        "INSERT INTO bots (agent_name, bot_token, registration_link, channel_link, play_url, video_url, image_url, bot_role, created_by) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    )
                    cursor.execute(sql, (agent_name, token, reg_link, channel_link, play_url, video_url, image_url, bot_role, created_by))
                    conn.commit()
                    bot_id = cursor.lastrowid
                    return get_bot_by_id(bot_id)
            except Exception:
                return None
        else:
            cursor = conn.cursor()
            sql = (
                "INSERT INTO bots (agent_name, bot_token, registration_link, channel_link, play_url, video_url, image_url, bot_role, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            cursor.execute(sql, (agent_name, token, reg_link, channel_link, play_url, video_url, image_url, bot_role, created_by))
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


def update_play_url(token: str, play_url: str) -> bool:
    """更新指定机器人的 play_url。返回是否成功。"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("UPDATE bots SET play_url = %s WHERE bot_token = %s", (play_url, token))
                conn.commit()
                return cursor.rowcount > 0
        else:
            cursor = conn.cursor()
            cursor.execute("UPDATE bots SET play_url = ? WHERE bot_token = ?", (play_url, token))
            conn.commit()
            return cursor.rowcount > 0
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


def get_bots_by_creator(created_by: int, role: str | None = None):
    """按创建者（运营）查询机器人，可选按角色筛选。"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                if role:
                    cursor.execute("SELECT * FROM bots WHERE created_by = %s AND bot_role = %s", (created_by, role))
                else:
                    cursor.execute("SELECT * FROM bots WHERE created_by = %s", (created_by,))
                return cursor.fetchall()
        else:
            cursor = conn.cursor()
            if role:
                cursor.execute("SELECT * FROM bots WHERE created_by = ? AND bot_role = ?", (created_by, role))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            else:
                cursor.execute("SELECT * FROM bots WHERE created_by = ?", (created_by,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
    finally:
        conn.close()


def count_users_for_bot(bot_token: str) -> int:
    """统计在 user_conversations 中出现过的唯一 chat_id 数量，视为“点进来过”。"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(DISTINCT chat_id) FROM user_conversations WHERE bot_token = %s", (bot_token,))
                row = cursor.fetchone()
                return int(row[0] if isinstance(row, (list, tuple)) else list(row.values())[0])
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(DISTINCT chat_id) FROM user_conversations WHERE bot_token = ?", (bot_token,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def get_unclaimed_bots(role: str | None = None):
    """查询 created_by 为空/NULL 的历史机器人。"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                if role:
                    cursor.execute("SELECT * FROM bots WHERE created_by IS NULL AND bot_role = %s", (role,))
                else:
                    cursor.execute("SELECT * FROM bots WHERE created_by IS NULL")
                return cursor.fetchall()
        else:
            cursor = conn.cursor()
            if role:
                cursor.execute("SELECT * FROM bots WHERE created_by IS NULL AND bot_role = ?", (role,))
            else:
                cursor.execute("SELECT * FROM bots WHERE created_by IS NULL")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def claim_bot_owner(bot_token: str, operator_id: int) -> bool:
    """为一个 created_by 为空的机器人设置归属。返回是否成功。"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("UPDATE bots SET created_by = %s WHERE bot_token = %s AND (created_by IS NULL)", (operator_id, bot_token))
                conn.commit()
                return cursor.rowcount > 0
        else:
            cursor = conn.cursor()
            cursor.execute("UPDATE bots SET created_by = ? WHERE bot_token = ? AND (created_by IS NULL)", (operator_id, bot_token))
            conn.commit()
            return cursor.rowcount > 0
    finally:
        conn.close()


def claim_all_unowned(operator_id: int, role: str | None = None) -> int:
    """批量为未认领机器人设置归属，返回受影响数量。可按角色过滤。"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                if role:
                    cursor.execute("UPDATE bots SET created_by = %s WHERE created_by IS NULL AND bot_role = %s", (operator_id, role))
                else:
                    cursor.execute("UPDATE bots SET created_by = %s WHERE created_by IS NULL", (operator_id,))
                conn.commit()
                return cursor.rowcount
        else:
            cursor = conn.cursor()
            if role:
                cursor.execute("UPDATE bots SET created_by = ? WHERE created_by IS NULL AND bot_role = ?", (operator_id, role))
            else:
                cursor.execute("UPDATE bots SET created_by = ? WHERE created_by IS NULL", (operator_id,))
            conn.commit()
            return cursor.rowcount
    finally:
        conn.close()


def claim_bot_owner_by_id(bot_id: int, operator_id: int) -> bool:
    """按 id 认领（created_by 为空时生效）。"""
    conn = get_db_connection()
    try:
        if DB_BACKEND == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("UPDATE bots SET created_by = %s WHERE id = %s AND (created_by IS NULL)", (operator_id, bot_id))
                conn.commit()
                return cursor.rowcount > 0
        else:
            cursor = conn.cursor()
            cursor.execute("UPDATE bots SET created_by = ? WHERE id = ? AND (created_by IS NULL)", (operator_id, bot_id))
            conn.commit()
            return cursor.rowcount > 0
    finally:
        conn.close()
