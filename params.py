import logging
from pathlib import Path
from telegram.ext import ContextTypes
from afubot.bot import database as afu_db

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent
TGS_DIR = ROOT / "tgsfile"

async def tgs_file(context: ContextTypes.DEFAULT_TYPE, name: str) -> bool:
    # 扩展：支持 .tgs/.webp/.webm；优先复用已缓存的 file_id；兼容旧 key
    try:
        bot_conf = context.bot_data.get("bot_config") or {}
        token = bot_conf.get("bot_token")
        chat_id = context.bot_data["target_chat_id"]  # 频道用这个；私聊请传你自己的 chat_id

        exts = [".tgs", ".webp", ".webm"]

        # 1) 先尝试带后缀的缓存（更精确）
        for ext in exts:
            k = f"sticker:{name}{ext}"
            fid = afu_db.get_media_file_id(token, k)
            if fid:
                await context.bot.send_sticker(chat_id=chat_id, sticker=fid)
                return True

        # 2) 兼容旧键（无后缀）
        legacy_key = f"sticker:{name}"
        legacy_fid = afu_db.get_media_file_id(token, legacy_key)
        if legacy_fid:
            await context.bot.send_sticker(chat_id=chat_id, sticker=legacy_fid)
            return True

        # 3) 本地文件首发：按优先顺序查找存在的文件
        for ext in exts:
            p = TGS_DIR / f"{name}{ext}"
            if p.exists():
                with p.open("rb") as f:
                    msg = await context.bot.send_sticker(chat_id=chat_id, sticker=f)
                got = getattr(getattr(msg, "sticker", None), "file_id", None)
                if got:
                    afu_db.upsert_media_file_id(token, f"sticker:{name}{ext}", got)
                return True

        logger.warning("sticker not found for %s (tried %s)", name, exts)
        return False
    except Exception as e:
        logger.warning("params(%s) failed: %s", name, e)
        return False


async def image_file(context: ContextTypes.DEFAULT_TYPE, name: str) -> bool:
    """发送本地图片（.jpg/.jpeg/.png），并缓存 file_id。

    使用方式：将文件放入 tgsfile/ 下，如 cat.jpg → await image_file(context, "cat")
    """
    try:
        bot_conf = context.bot_data.get("bot_config") or {}
        token = bot_conf.get("bot_token")
        chat_id = context.bot_data["target_chat_id"]

        exts = [".jpg", ".jpeg", ".png"]

        # 1) 尝试带后缀的缓存
        for ext in exts:
            key = f"photo:{name}{ext}"
            fid = afu_db.get_media_file_id(token, key)
            if fid:
                await context.bot.send_photo(chat_id=chat_id, photo=fid)
                return True

        # 2) 兼容旧键（无后缀）
        legacy_key = f"photo:{name}"
        legacy_fid = afu_db.get_media_file_id(token, legacy_key)
        if legacy_fid:
            await context.bot.send_photo(chat_id=chat_id, photo=legacy_fid)
            return True

        # 3) 本地首发
        for ext in exts:
            p = TGS_DIR / f"{name}{ext}"
            if p.exists():
                with p.open("rb") as f:
                    msg = await context.bot.send_photo(chat_id=chat_id, photo=f)
                # send_photo 返回的 Message.photo 是尺寸列表，取最后一个
                try:
                    sizes = getattr(msg, "photo", None) or []
                    file_id = sizes[-1].file_id if sizes else None
                except Exception:
                    file_id = None
                if file_id:
                    afu_db.upsert_media_file_id(token, f"photo:{name}{ext}", file_id)
                return True

        logger.warning("image not found for %s (tried %s)", name, exts)
        return False
    except Exception as e:
        logger.warning("image_file(%s) failed: %s", name, e)
        return False