import asyncio
import logging
import random
import re
import time
from . import config
from . import database
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.error import RetryAfter, TimedOut, NetworkError, BadRequest
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
AWAITING_ID, AWAITING_RECHARGE_CONFIRM, AWAITING_REGISTER_CONFIRM = range(3)
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


# --- 新增：注册确认/引导 ---
async def _send_register_prompt(update_or_context, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    keyboard = [[
        InlineKeyboardButton("Yes✅", callback_data="reg_yes"),
        InlineKeyboardButton("No🧩", callback_data="reg_no")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await _retry_send(lambda: context.bot.send_message(
        chat_id=chat_id,
        text="Bhai, registration ho gaya? ✅\nHo gaya to 'Yes' dabao, warna 'No' par click karo – main guide karta hoon 🚀",
        reply_markup=reply_markup
    ))


async def _proceed_deposit_and_final(context: ContextTypes.DEFAULT_TYPE, chat_id: int, bot_config: dict):
    # 第四步：存款与视频（Hinglish 文案）
    lines = [
        "Chalo ab turant Deposit 💳 par click karo, minimum 100 deposit karo. Main tumhe sikhata hoon kaise 100 ko 10000 me badalna hai! 💥 Phir main tumhe prediction robot 🤖 dunga – simple!",
        "\nBhai, tum goal ke bahut kareeb ho 🎯. Aaj ek kadam badhao, future wala tum khud ko thank karega 🙏.",
        "\nMauka saamne hai, success bas ek kadam door 🏁. Doubt mat karo, abhi action lo ⚡!",
    ]
    for t in lines:
        await human_send_message(context, chat_id, t)

    # 存款教学视频
    try:
        deposit_video_url = random.choice(config.IMAGE_LIBRARY['deposit_guide'])
        deposit_file_id = bot_config.get('deposit_file_id')
        await indicate_action(context, chat_id, ChatAction.UPLOAD_VIDEO, random.uniform(0.4, 0.8))
        if deposit_file_id:
            await _retry_send(lambda: context.bot.send_video(chat_id=chat_id, video=deposit_file_id))
        else:
            msg = await send_video_with_cache(context, chat_id, deposit_video_url)
            try:
                fid = getattr(getattr(msg, 'video', None), 'file_id', None)
                if fid:
                    database.update_bot_file_ids(bot_config['bot_token'], deposit_file_id=fid)
                    bot_config['deposit_file_id'] = fid
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to send deposit guide: {e}")

    await asyncio.sleep(3)

    # 最后一步：进入频道
    channel_link = bot_config.get('channel_link') or 'Channel link not configured'
    final_text = (
        "Last step! 🏁\n"
        "👉 Prediction Robot channel join karo aur bell on karo 🔔\n"
        "Wahan main useful tips 🛠️ regular share karunga,\n"
        "taaki tum step‑by‑step seekho aur kamao 🚀\n"
        f"{channel_link}"
    )
    await human_send_message(context, chat_id, final_text)


# --- 对话流程函数 ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """处理 /start 命令，作为对话的入口点（重写为分步脚本）"""
    chat_id = update.effective_chat.id
    bot_config = context.bot_data.get('config', {})

    # 第一步：图片 + 文案
    try:
        first_image_url = random.choice(config.IMAGE_LIBRARY['firstpng'])
        await indicate_action(context, chat_id, ChatAction.UPLOAD_PHOTO, random.uniform(0.3, 0.6))
        await send_photo_with_cache(context, chat_id, first_image_url)
    except Exception as e:
        logger.warning(f"Failed to send first guide image: {e}")

    first_copy = (
        "Guys, dhyaan se suno 🚨 Aaj main apna wealth secret share kar raha hoon 💰 – cars 🏎️, cash 💵, gold 🏆\n"
        "Yeh sab aasman se nahi gira, black‑tech prediction robot 🤖 se kamaaya!\n"
        "Isi ne mujhe step‑by‑step wealth ceiling todne me madad ki 💥\n"
        "Aur mujhe mila – financial freedom 🤑\n"
        "Kya tum bhi mere jaise financial freedom chahte ho? 💸\n"
        "Bas mere steps follow karo, ek‑ek karke, tum bhi kar sakte ho ✅\n"
        "Ready ho? 🔥"
    )
    await human_send_message(context, chat_id, first_copy)

    await asyncio.sleep(random.uniform(1, 3))

    # 第二步：注册（Hinglish）
    registration_link = bot_config.get('registration_link', 'Registration link not configured')
    step2 = (
        "Ab main tumhe step‑by‑step guide karunga 🧭\n"
        "Step 1: Registration complete karo 📝\n"
        f"Neeche wala link click karo 👇\n{registration_link}\n"
        "Register ho jao, phir next step unlock hoga 🔓"
    )
    await human_send_message(context, chat_id, step2)

    await asyncio.sleep(random.uniform(2, 3))

    # 第三步：确认是否已注册（按钮）
    await _send_register_prompt(update, context, chat_id)
    return AWAITING_REGISTER_CONFIRM


async def handle_register_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # 回调按钮容错：旧/无效 query 直接友好提示并结束
    try:
        await query.answer()
    except BadRequest as e:
        text = str(e).lower()
        if "query is too old" in text or "query id is invalid" in text:
            try:
                await context.bot.send_message(chat_id=query.message.chat_id, text="Bhai, yeh button expire ho chuka hai. /start bhejo aur fir se shuru karo ✅")
            except Exception:
                pass
            return ConversationHandler.END
        else:
            raise
    choice = query.data
    chat_id = query.message.chat_id
    bot_config = context.bot_data.get('config', {})

    if choice == 'reg_yes':
        # 进入第四步
        await query.edit_message_reply_markup(reply_markup=None)
        await asyncio.sleep(random.uniform(1, 2))
        await _proceed_deposit_and_final(context, chat_id, bot_config)
        return ConversationHandler.END
    else:
        # No：连发三条引导语（Hinglish），每条间隔1秒，然后再给按钮
        await query.edit_message_reply_markup(reply_markup=None)
        guides = [
            "Zyada sochne se kuch nahi badalta 🤔. Pehle account register karo, main turant sikhaunga ki robot se paise kaise banane hain 💹. Ready? 🔥",
            "Mauka sirf ek baar aata hai, abhi bhi kis baat ka intezaar? ⏳",
            "Pehla kadam nahi loge to kabhi nahi pata chalega ki kitna aasan hai 👣.",
        ]
        for t in guides:
            await human_send_message(context, chat_id, t)
            await asyncio.sleep(1)
        await _send_register_prompt(update, context, chat_id)
        return AWAITING_REGISTER_CONFIRM


# 保留旧的ID与充值确认逻辑（当前不再进入）

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
    # 回调按钮容错：旧/无效 query 直接忽略并提示
    try:
        await query.answer()
    except BadRequest as e:
        text = str(e).lower()
        if "query is too old" in text or "query id is invalid" in text:
            try:
                await context.bot.send_message(chat_id=query.message.chat_id, text="Bhai, yeh button expire ho chuka hai. /start bhejo aur fir se shuru karo ✅")
            except Exception:
                pass
            return ConversationHandler.END
        else:
            raise

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
    channel_link = bot_config.get('channel_link') or 'Channel link not configured'
    final_message = (
        "Access open ho chuka hai. Ab channel join karke signal follow karo:\n"
        f"{channel_link}"
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
        AWAITING_REGISTER_CONFIRM: [CallbackQueryHandler(handle_register_decision, pattern="^reg_(yes|no)$")],
        AWAITING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id)],
        AWAITING_RECHARGE_CONFIRM: [CallbackQueryHandler(handle_recharge_confirm, pattern="^confirm_recharge_yes$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=3600  # 1小时后对话自动超时结束
)
