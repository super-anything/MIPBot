import logging
from pathlib import Path
from telegram.ext import ContextTypes
from afubot.bot import database as afu_db

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent
TGS_DIR = ROOT / "tgsfile"

async def tgs_file(context: ContextTypes.DEFAULT_TYPE, name: str) -> bool:
    # 通用：先用 KV 表的 file_id；没有就用本地 name.tgs 首发并写回
    try:
        bot_conf = context.bot_data.get("bot_config") or {}
        token = bot_conf.get("bot_token")
        chat_id = context.bot_data["target_chat_id"]  # 频道用这个；私聊请传你自己的 chat_id
        media_key = f"sticker:{name}"

        fid = afu_db.get_media_file_id(token, media_key)
        if fid:
            await context.bot.send_sticker(chat_id=chat_id, sticker=fid)
            return True

        p = TGS_DIR / f"{name}.tgs"
        if not p.exists():
            logger.warning("tgs not found: %s", p)
            return False

        with p.open("rb") as f:
            msg = await context.bot.send_sticker(chat_id=chat_id, sticker=f)
        got = getattr(getattr(msg, "sticker", None), "file_id", None)
        if got:
            afu_db.upsert_media_file_id(token, media_key, got)
        return True
    except Exception as e:
        logger.warning("params(%s) failed: %s", name, e)
        return False