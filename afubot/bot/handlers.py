import asyncio
import logging
import random
import re
import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
NAG_INTERVAL_SECONDS = 30
MAX_NAG_ATTEMPTS = 6


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

    keyboard = [[InlineKeyboardButton("Yes", callback_data="confirm_recharge_yes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text="Bro, have you completed the recharge? Once done, you can start using the Prediction Bot right away!",
                                   reply_markup=reply_markup)

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

    # 1. 发送欢迎视频 (如果配置了)
    video_url = bot_config.get('video_url')
    if video_url:
        try:
            await context.bot.send_video(chat_id=chat_id, video=video_url)
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Failed to send video from URL (URL: {video_url}): {e}")

    # 2. 逐步发送欢迎消息
    await context.bot.send_message(chat_id=chat_id,
                                   text="Hi guys, thanks for your continued support and presence. Today, I'm officially opening up a special space for you, where we can interact more closely.")
    await asyncio.sleep(5)
    await context.bot.send_message(chat_id=chat_id, text="This is not just a place for interaction, but also the only channel for fans' exclusive benefits.")
    await asyncio.sleep(5)

    benefits_text = (
        "To thank you for your long-term support, I have prepared multiple benefits:\n 1、[An exclusive hacker bot with up to 90% accuracy],\n 2、[Cash prize drawing],\n 3、[Mobile phone prizes].\n\n Please note:\n You only have a chance to get exclusive benefits after completing these two things."
    )
    await context.bot.send_message(chat_id=chat_id, text=benefits_text)
    await asyncio.sleep(5)

    # 3. 发送注册链接
    registration_link = bot_config.get('registration_link', '（Registration link not configured）')

    await context.bot.send_message(chat_id=chat_id,
                                   text=f"First: Click my exclusive link to register and unlock exclusive fan benefits!\n{registration_link}")

    try:
        # 从配置中随机选择一张引导图
        find_id_image_url = random.choice(config.IMAGE_LIBRARY['find_id'])
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=find_id_image_url,
            caption="After completing the registration, please refer to the image above to find your 9-digit ID."
        )
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"Failed to send 'find_id' image, please check config.py configuration: {e}")

    await asyncio.sleep(10)
    await context.bot.send_message(chat_id=chat_id,
                                   text="Bro, have you completed the registration? Send me the ID, and I'll open a backdoor for your account.")

    return AWAITING_ID


async def handle_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """处理并验证用户发送的ID"""
    user_id_input = update.message.text
    chat_id = update.message.chat_id

    if not re.match(r'^\d{9}$', user_id_input):
        await update.message.reply_text("User ID not found, please continue to send the correct ID.")
        return AWAITING_ID

    await asyncio.sleep(10)
    # The message you provided
    await update.message.reply_text("Zabardast! You have successfully joined the exclusive channel! Bas, just a recharge of [200] rupees more, and you can unlock the Prediction Bot... Fatafat!")

    try:
        # --- 关键修改：直接从导入的config模块读取 ---
        deposit_video_url = random.choice(config.IMAGE_LIBRARY['deposit_guide'])
        await context.bot.send_video(
            chat_id=chat_id,
            video=deposit_video_url,
            caption="Please watch this video to learn how to complete the recharge safely and quickly."
        )
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"Failed to send 'deposit_guide' video, please check config.py configuration: {e}")

    keyboard = [[InlineKeyboardButton("Yes", callback_data="confirm_recharge_yes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Bro, have you completed the recharge? Once done, you can start using the Prediction Bot right away!",
                                    reply_markup=reply_markup)

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
    await asyncio.sleep(5)

    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text="Second: Great! I'm immediately unlocking the Prediction Bot with up to 90% accuracy for you. Get ready for a high-reward journey!")
    await asyncio.sleep(5)

    bot_config = context.bot_data.get('config', {})
    prediction_bot_link = bot_config.get('prediction_bot_link', '（Prediction Bot link not configured）')

    final_message = (
        "The system is pushing the first batch of prediction data for you, with an accuracy of 90%+!\n"
        "These precise predictions will bring you higher returns and continuous income,\n"
        "The opportunity is right in front of you! Click the link below to enter the bot immediately,\n"
        "Take a step ahead on the path to high income!\n"
        f"{prediction_bot_link}"
    )
    await context.bot.send_message(chat_id=query.message.chat_id, text=final_message)

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
