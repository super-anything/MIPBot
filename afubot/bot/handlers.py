import asyncio
import logging
import re
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
AWAITING_JOIN_CONFIRM, AWAITING_ID, AWAITING_RECHARGE_CONFIRM = range(3)
NAG_INTERVAL_SECONDS = 10
MAX_NAG_ATTEMPTS = 6


# --- 定时提醒函数 ---

async def nag_join_callback(context: ContextTypes.DEFAULT_TYPE):
    """定时提醒用户确认加入频道"""
    job = context.job
    chat_id, user_id = job.chat_id, job.user_id
    nag_attempts = context.user_data.get('join_nag_attempts', 0)

    if nag_attempts >= MAX_NAG_ATTEMPTS:
        context.user_data.pop(f'join_nag_job_name_{user_id}', None)
        context.user_data.pop('join_nag_attempts', None)
        return

    keyboard = [[InlineKeyboardButton("yes", callback_data="confirm_join_yes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id,
                                   text="兄弟，只有群成员才有机会获取专属福利。你已经加入了我的粉丝群了吗？",
                                   reply_markup=reply_markup)

    context.user_data['join_nag_attempts'] = nag_attempts + 1
    job_name = f'join_nag_{chat_id}_{user_id}'
    context.job_queue.run_once(nag_join_callback, NAG_INTERVAL_SECONDS, chat_id=chat_id, user_id=user_id, name=job_name)
    context.user_data[f'join_nag_job_name_{user_id}'] = job_name


async def nag_recharge_callback(context: ContextTypes.DEFAULT_TYPE):
    """定时提醒用户确认充值"""
    job = context.job
    chat_id, user_id = job.chat_id, job.user_id
    nag_attempts = context.user_data.get('recharge_nag_attempts', 0)

    if nag_attempts >= MAX_NAG_ATTEMPTS:
        context.user_data.pop(f'recharge_nag_job_name_{user_id}', None)
        context.user_data.pop('recharge_nag_attempts', None)
        return

    keyboard = [[InlineKeyboardButton("yes", callback_data="confirm_recharge_yes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text="兄弟，你完成充值了吗？一旦完成，就可以马上使用预测机器人了！",
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

    # 清理可能存在的旧任务
    job_name_key = f'join_nag_job_name_{user_id}'
    if job_name_key in context.user_data:
        jobs = context.job_queue.get_jobs_by_name(context.user_data[job_name_key])
        for job in jobs:
            job.schedule_removal()

    bot_config = context.bot_data.get('config', {})

    # 1. 发送欢迎视频 (如果配置了)
    video_url = bot_config.get('video_url')
    if video_url:
        try:
            await context.bot.send_video(chat_id=chat_id, video=video_url)
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"通过URL发送视频失败 (URL: {video_url}): {e}")

    # 2. 逐步发送欢迎消息
    await context.bot.send_message(chat_id=chat_id,
                                   text="亲爱的朋友们，感谢大家一直以来的支持与陪伴。今天，我正式为大家开启一个专属空间，在这里我们能够更加紧密地互动交流。")
    await asyncio.sleep(1)
    await context.bot.send_message(chat_id=chat_id, text="这里不仅仅是互动的场所，更是粉丝专属福利的唯一通道。")
    await asyncio.sleep(1)

    benefits_text = (
        "为了感谢长期以来的支持，我准备了多重福利：\n 1、[准确率高达90%的专属黑客机器人]，\n 2、[现金奖励抽取]，\n 3、[手机奖励]。\n\n 请注意：\n 只有完成以下两件事，才有机会获取专属福利")
    await context.bot.send_message(chat_id=chat_id, text=benefits_text)
    await asyncio.sleep(1)

    # 3. 发送频道链接
    channel_link = bot_config.get('channel_link', '（频道链接未配置）')
    await context.bot.send_message(chat_id=chat_id, text=f"第一步：立即点击链接加入电报频道（{channel_link}）。")
    await asyncio.sleep(3)

    # 4. 发送确认按钮并启动提醒
    keyboard = [[InlineKeyboardButton("yes", callback_data="confirm_join_yes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("兄弟，只有群成员才有机会获取专属福利。你已经加入了我的粉丝群了吗？",
                                    reply_markup=reply_markup)

    context.user_data['join_nag_attempts'] = 0
    job_name = f'join_nag_{chat_id}_{user_id}'
    context.job_queue.run_once(nag_join_callback, NAG_INTERVAL_SECONDS, chat_id=chat_id, user_id=user_id, name=job_name)
    context.user_data[job_name_key] = job_name

    return AWAITING_JOIN_CONFIRM


async def handle_join_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """处理用户确认加入频道"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    # 清理提醒任务
    job_name_key = f'join_nag_job_name_{user_id}'
    if job_name_key in context.user_data:
        jobs = context.job_queue.get_jobs_by_name(context.user_data[job_name_key])
        for job in jobs:
            job.schedule_removal()
        context.user_data.pop(job_name_key, None)

    await query.edit_message_reply_markup(reply_markup=None)
    await asyncio.sleep(1)

    bot_config = context.bot_data.get('config', {})
    agent_link = bot_config.get('registration_link', '（未配置代理链接）')


    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text=f"非常好，接下来是第二步：点击我的专属链接注册，解锁专属的粉丝福利！\n{agent_link}")

    await asyncio.sleep(3)
    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text="兄弟，你完成注册了吗？ID发给我，我给你的账号开个后门。")

    return AWAITING_ID


async def handle_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """处理并验证用户发送的ID"""
    user_id_input = update.message.text
    chat_id = update.message.chat_id

    if not re.match(r'^\d{9}$', user_id_input):
        await update.message.reply_text("用户id未查询到，请继续发送正确的ID。")
        return AWAITING_ID

    await asyncio.sleep(1)
    await update.message.reply_text("太棒了！你已成功加入专属通道。\n只需要再充值[200] 卢比，即可立即解锁 预测机器人！")

    await asyncio.sleep(1)
    bot_config = context.bot_data.get('config', {})
    image_file_id = bot_config.get('image_url')
    if image_file_id:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=image_file_id)
        except Exception as e:
            logger.error(f"发送图片失败 (file_id: {image_file_id}): {e}")

    await asyncio.sleep(3)

    keyboard = [[InlineKeyboardButton("yes", callback_data="confirm_recharge_yes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("兄弟，你完成充值了吗？一旦完成，就可以马上使用预测机器人了！",
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
    await asyncio.sleep(2)

    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text="兄弟，太给力了！马上为你解锁准确率高达90%的预测机器人，准备好迎接高回报的旅程吧！")
    await asyncio.sleep(2)

    bot_config = context.bot_data.get('config', {})
    prediction_bot_link = bot_config.get('prediction_bot_link', '（预测机器人链接未配置）')

    final_message = (
        "系统正在为您推送第一波预测数据，准确率高达 90%+！\n"
        "这些精准预测将为您带来 更高回报与持续收入，\n"
        "机会就在眼前! 点击下方链接立即进入机器人，\n"
        "抢先一步开启高收益之路!\n"
        f"{prediction_bot_link}"
    )
    await context.bot.send_message(chat_id=query.message.chat_id, text=final_message)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """取消对话"""
    await update.message.reply_text("对话已取消。发送 /start 重新开始。")
    # 清理所有可能的任务
    user_id = update.effective_user.id
    for key_prefix in ['join_nag_job_name_', 'recharge_nag_job_name_']:
        job_name_key = f'{key_prefix}{user_id}'
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
        AWAITING_JOIN_CONFIRM: [CallbackQueryHandler(handle_join_confirm, pattern="^confirm_join_yes$")],
        AWAITING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id)],
        AWAITING_RECHARGE_CONFIRM: [CallbackQueryHandler(handle_recharge_confirm, pattern="^confirm_recharge_yes$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=3600  # 1小时后对话自动超时结束
)
