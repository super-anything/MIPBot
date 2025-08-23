import asyncio
import logging
import random
import re
import time
import config
import database
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.error import RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler
)

logger = logging.getLogger(__name__)

# --- 对话状态定义 ---
AWAITING_ID, AWAITING_RECHARGE_CONFIRM = range(2)
NAG_INTERVAL_SECONDS = 10
MAX_NAG_ATTEMPTS = 6

# --- 发送优化：重试与文件ID缓存 ---
SEND_RETRY_ATTEMPTS = 2
SEND_RETRY_BACKOFF_SECONDS = 0.8


async def _retry_send(send_coro_factory):
    """对发送动作进行有限次重试，并优先遵循 Telegram 的 Retry-After。"""
    last_exc = None
    for attempt in range(1, SEND_RETRY_ATTEMPTS + 2):  # 初次 + 重试次数
        try:
            return await send_coro_factory()
        except RetryAfter as exc:  # 遵循服务端节流建议
            wait_secs = float(getattr(exc, 'retry_after', 1)) + random.uniform(0.3, 0.9)
            await asyncio.sleep(wait_secs)
            last_exc = exc
        except (TimedOut, NetworkError) as exc:
            backoff = min(2.0 ** attempt * 0.3, 3.0) + random.uniform(0.1, 0.4)
            await asyncio.sleep(backoff)
            last_exc = exc
        except Exception as exc:  # 需要兜底所有发送异常
            last_exc = exc
            if attempt <= SEND_RETRY_ATTEMPTS:
                await asyncio.sleep(SEND_RETRY_BACKOFF_SECONDS * attempt)
            else:
                raise last_exc
    raise last_exc


def _get_fileid_cache(context: ContextTypes.DEFAULT_TYPE):
    cache = context.application.bot_data.get('file_id_cache')
    if cache is None:
        cache = {}
        context.application.bot_data['file_id_cache'] = cache
    return cache


async def send_video_with_cache(context: ContextTypes.DEFAULT_TYPE, chat_id, url, caption=None):
    """优先使用已缓存的 file_id 发送视频，失败则回退到 URL 并缓存。"""
    cache = _get_fileid_cache(context)
    cached_file_id = cache.get(url)

    async def _send_with_id():
        return await context.bot.send_video(chat_id=chat_id, video=cached_file_id, caption=caption)

    async def _send_with_url():
        return await context.bot.send_video(chat_id=chat_id, video=url, caption=caption)

    message = None
    if cached_file_id:
        try:
            message = await _retry_send(_send_with_id)
        except Exception:
            message = await _retry_send(_send_with_url)
    else:
        message = await _retry_send(_send_with_url)

    try:
        if getattr(message, 'video', None) and getattr(message.video, 'file_id', None):
            cache[url] = message.video.file_id
    except Exception:
        pass
    return message


async def send_photo_with_cache(context: ContextTypes.DEFAULT_TYPE, chat_id, url, caption=None):
    """优先使用已缓存的 file_id 发送图片，失败则回退到 URL 并缓存。"""
    cache = _get_fileid_cache(context)
    cached_file_id = cache.get(url)

    async def _send_with_id():
        return await context.bot.send_photo(chat_id=chat_id, photo=cached_file_id, caption=caption)

    async def _send_with_url():
        return await context.bot.send_photo(chat_id=chat_id, photo=url, caption=caption)

    message = None
    if cached_file_id:
        try:
            message = await _retry_send(_send_with_id)
        except Exception:
            message = await _retry_send(_send_with_url)
    else:
        message = await _retry_send(_send_with_url)

    try:
        if getattr(message, 'photo', None):
            cache[url] = message.photo[-1].file_id
    except Exception:
        pass
    return message


# --- 人性化发送辅助 ---
def _estimate_typing_seconds_fast(text: str) -> float:
    length = len(text or "")
    base = max(0.0, length / random.uniform(28.0, 36.0))
    jitter = random.uniform(0.05, 0.2)
    return max(0.15, min(0.45, base + jitter))


def _estimate_typing_seconds_slow(text: str) -> float:
    length = len(text or "")
    base = max(0.0, length / random.uniform(14.0, 20.0))
    jitter = random.uniform(0.3, 0.7)
    return max(0.8, min(1.8, base + jitter)) + 1.0


async def indicate_action(context: ContextTypes.DEFAULT_TYPE, chat_id, action: ChatAction, seconds: float | None = None):
    try:
        await _retry_send(lambda: context.bot.send_chat_action(chat_id=chat_id, action=action))
        await asyncio.sleep(seconds if seconds is not None else random.uniform(0.5, 1.1))
    except Exception:
        # 忽略动作失败
        pass


async def human_send_message(context: ContextTypes.DEFAULT_TYPE, chat_id, text: str, parse_mode: str | None = None):
    # 首条消息：快速；其后：更长的拟人延时
    if not context.user_data.get('first_text_sent'):
        seconds = _estimate_typing_seconds_fast(text)
        context.user_data['first_text_sent'] = True
    else:
        seconds = _estimate_typing_seconds_slow(text)
    await indicate_action(context, chat_id, ChatAction.TYPING, seconds)
    return await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode))

# --- 定时提醒函数 ---

async def nag_recharge_callback(context: ContextTypes.DEFAULT_TYPE):
    """定时提醒用户确认充值"""
    job = context.job
    chat_id, user_id = job.chat_id, job.user_id
    nag_attempts = context.user_data.get('recharge_nag_attempts', 0)

    if nag_attempts >= MAX_NAG_ATTEMPTS:
        context.user_data.pop(f'recharge_nag_job_name_{user_id}', None)
        context.user_data.pop('recharge_nag_attempts', None)
        return

    keyboard = [[InlineKeyboardButton("Recharge ho gaya ✅", callback_data="confirm_recharge_yes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text="Bhai, recharge complete ho gaya? Ho gaya ho to niche button dabao, main turant access de deta hoon.", reply_markup=reply_markup))

    context.user_data['recharge_nag_attempts'] = nag_attempts + 1
    job_name = f'recharge_nag_{chat_id}_{user_id}'
    context.job_queue.run_once(nag_recharge_callback, NAG_INTERVAL_SECONDS, chat_id=chat_id, user_id=user_id,
                               name=job_name)
    context.user_data[f'recharge_nag_job_name_{user_id}'] = job_name


# --- 对话流程函数 ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """处理 /start 命令，作为对话的入口点"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    bot_config = context.bot_data.get('config', {})

    # 0. 个性化称呼与问候
    user_name = (update.effective_user.first_name or "dost").strip()
    hour = time.localtime().tm_hour
    greeting = "Good morning" if 5 <= hour < 12 else ("Good afternoon" if 12 <= hour < 18 else "Good evening")

    # 1. 首发：先发送引导图片（同步发送，确保用户第一眼就看到）
    try:
        first_image_url = random.choice(config.IMAGE_LIBRARY['firstpng'])
        await indicate_action(context, chat_id, ChatAction.UPLOAD_PHOTO, random.uniform(0.3, 0.6))
        await send_photo_with_cache(context, chat_id, first_image_url)
    except Exception as e:
        logger.warning(f"Failed to send first guide image: {e}")

    # 2. 立即先发首条文本
    welcome_text = f"{greeting}, {user_name}! Aapka support ke liye shukriya. Maine yahan ek chhota exclusive space banaya hai jahan hum aur closely connect kar sakte hain."
    await human_send_message(context, chat_id, welcome_text)

    benefits_text = (
        "Yahan pe kuch exclusive benefits ready hain:\n"
        "1) High-accuracy prediction bot;\n"
        "2) Cash rewards lucky draw;\n"
        "3) Mobile giveaways.\n\n"
        "Bas 2 simple steps complete karo, aur sab unlock ho jayega."
    )
    await human_send_message(context, chat_id, benefits_text)

    # 3. 发送注册链接
    registration_link = bot_config.get('registration_link', 'Registration link not configured')
    await human_send_message(context, chat_id, f"Step 1: Mere exclusive link se register karo 👇\n{registration_link}")

    # 4. 将媒体发送放到后台，不阻塞文本到达
    video_url = bot_config.get('video_url')
    video_file_id = bot_config.get('video_file_id')
    if video_url:
        async def _bg_send_video():
            try:
                await indicate_action(context, chat_id, ChatAction.UPLOAD_VIDEO, random.uniform(0.4, 0.8))
                if video_file_id:
                    # 优先用持久化 file_id
                    msg = await _retry_send(lambda: context.bot.send_video(chat_id=chat_id, video=video_file_id))
                else:
                    msg = await send_video_with_cache(context, chat_id, video_url)
                    # 首次成功后持久化
                    try:
                        fid = getattr(getattr(msg, 'video', None), 'file_id', None)
                        if fid:
                            database.update_bot_file_ids(bot_config['bot_token'], video_file_id=fid)
                            bot_config['video_file_id'] = fid
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Failed to send video from URL (URL: {video_url}): {e}")
        asyncio.create_task(_bg_send_video())

    try:
        # 从配置中随机选择一张引导图
        find_id_image_url = random.choice(config.IMAGE_LIBRARY['find_id'])
        image_file_id = bot_config.get('image_file_id')
        async def _bg_send_photo():
            try:
                await indicate_action(context, chat_id, ChatAction.UPLOAD_PHOTO, random.uniform(0.4, 0.8))
                if image_file_id:
                    msg = await _retry_send(lambda: context.bot.send_photo(chat_id=chat_id, photo=image_file_id, caption="Registration ke baad, is image ko follow karke apna 9-digit ID dhoondo."))
                else:
                    msg = await send_photo_with_cache(context, chat_id, find_id_image_url, caption="Registration ke baad, is image ko follow karke apna 9-digit ID dhoondo.")
                    try:
                        pid = None
                        if getattr(msg, 'photo', None):
                            pid = msg.photo[-1].file_id
                        if pid:
                            database.update_bot_file_ids(bot_config['bot_token'], image_file_id=pid)
                            bot_config['image_file_id'] = pid
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Failed to send 'find_id' image, please check config.py configuration: {e}")
        asyncio.create_task(_bg_send_photo())
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"无法发送'find_id'图片，请检查config.py配置: {e}")

    await human_send_message(context, chat_id, "Register karne ke baad apna 9-digit ID bhej do. Main turant access open kar dunga.")

    return AWAITING_ID


async def handle_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """处理并验证用户发送的ID"""
    user_id_input = update.message.text
    chat_id = update.message.chat_id
    bot_config = context.bot_data.get('config', {})

    if not re.match(r'^\d{9}$', user_id_input):
        await _retry_send(lambda: update.message.reply_text("Ye 9-digit ID nahi lag raha. Fikr mat karo, sahi 9-digit ID bhej do bas."))
        return AWAITING_ID

    await _retry_send(lambda: update.message.reply_text("Great! Tumhara slot reserve kar diya. Ab sirf 200 rupees recharge karo, aur prediction bot turant unlock ho jayega."))

    try:
        # --- 关键修改：直接从导入的config模块读取 ---
        deposit_video_url = random.choice(config.IMAGE_LIBRARY['deposit_guide'])
        deposit_file_id = bot_config.get('deposit_file_id')
        if deposit_file_id:
            await _retry_send(lambda: context.bot.send_video(chat_id=chat_id, video=deposit_file_id, caption="Is video me safe aur fast recharge ka tareeqa dikhaya gaya hai."))
        else:
            msg = await send_video_with_cache(context, chat_id, deposit_video_url, caption="Is video me safe aur fast recharge ka tareeqa dikhaya gaya hai.")
            try:
                fid = getattr(getattr(msg, 'video', None), 'file_id', None)
                if fid:
                    database.update_bot_file_ids(bot_config['bot_token'], deposit_file_id=fid)
                    bot_config['deposit_file_id'] = fid
            except Exception:
                pass
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"Failed to send 'deposit_guide' video, please check config.py configuration: {e}")

    keyboard = [[InlineKeyboardButton("Recharge ho gaya ✅", callback_data="confirm_recharge_yes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await _retry_send(lambda: update.message.reply_text("Recharge complete ho jaye to niche button dabana, main access open kar dunga.", reply_markup=reply_markup))

    context.user_data['recharge_nag_attempts'] = 0
    job_name = f'recharge_nag_{chat_id}_{update.effective_user.id}'
    job_name_key = f'recharge_nag_job_name_{update.effective_user.id}'
    context.job_queue.run_once(nag_recharge_callback, NAG_INTERVAL_SECONDS, chat_id=chat_id,
                               user_id=update.effective_user.id, name=job_name)
    context.user_data[job_name_key] = job_name

    return AWAITING_RECHARGE_CONFIRM


async def handle_recharge_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """处理用户确认充值"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    # 清理提醒任务
    job_name_key = f'recharge_nag_job_name_{user_id}'
    if job_name_key in context.user_data:
        jobs = context.job_queue.get_jobs_by_name(context.user_data[job_name_key])
        for job in jobs:
            job.schedule_removal()
        context.user_data.pop(job_name_key, None)

    await query.edit_message_reply_markup(reply_markup=None)
    await human_send_message(context, query.message.chat_id, "Awesome! Ab main tumhare liye prediction bot unlock kar raha hoon (90%+ accuracy). Pehli wave ready hai!")

    bot_config = context.bot_data.get('config', {})
    prediction_bot_link = bot_config.get('prediction_bot_link', 'Prediction bot link not configured')

    final_message = (
        "First set of predictions tumhare liye push ho chuka hai (90%+).\n"
        "Zyada stable returns ke liye abhi join karo: \n"
        f"{prediction_bot_link}"
    )
    await human_send_message(context, query.message.chat_id, final_message)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """取消对话"""
    await update.message.reply_text("Conversation canceled. Send /start to restart.")
    # 清理所有可能的任务
    user_id = update.effective_user.id
    job_name_key = f'recharge_nag_job_name_{user_id}'
    if job_name_key in context.user_data:
        jobs = context.job_queue.get_jobs_by_name(context.user_data[job_name_key])
        for job in jobs:
            job.schedule_removal()
        context.user_data.pop(job_name_key, None)
    return ConversationHandler.END


# --- 构建总对话处理器 ---
conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        AWAITING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id)],
        AWAITING_RECHARGE_CONFIRM: [CallbackQueryHandler(handle_recharge_confirm, pattern="^confirm_recharge_yes$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=3600  # 1小时后对话自动超时结束
)
