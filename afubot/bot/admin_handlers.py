import logging
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
)

from . import config
from . import database
logger = logging.getLogger(__name__)

# --- 对话状态定义 ---
# 优化流程：先选择机器人类型，再根据类型收集相应信息
GETTING_AGENT_NAME, GETTING_BOT_TOKEN, GETTING_BOT_TYPE, GETTING_REG_LINK, GETTING_CHANNEL_LINK, GETTING_PLAY_URL, GETTING_VIDEO_URL, GETTING_IMAGE_URL = range(
    10, 18)

# 机器人类型常量
BOT_TYPE_GUIDE = 'private'  # 私聊引导注册类型
BOT_TYPE_CHANNEL = 'channel'  # 频道带单类型


# --- 权限检查 ---
def is_admin(update: Update) -> bool:
    return update.effective_user.id in config.ADMIN_USER_IDS


# --- 管理员指令 ---
async def start_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("抱歉，您无权使用此机器人。")
        return

    user_name = update.effective_user.first_name
    help_text = (
        f"👋 你好, {user_name}！\n\n"
        "欢迎使用代理机器人管理后台。\n\n"
        "你可以通过下方的【菜单】按钮或直接输入指令来操作：\n\n"
        "🔹 **/addbot** - 添加一个新的代理机器人\n"
        "🔹 **/listbots** - 查看所有代理机器人列表\n"
        "🔹 **/delbot** - 删除一个代理机器人\n"
        "🔹 **/help** - 显示此帮助信息\n"
        "🔹 **/cancel** - 取消当前操作"
    )
    await update.message.reply_text(help_text, parse_mode='HTML')


async def list_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    all_bots = database.get_all_bots()
    if not all_bots:
        await update.message.reply_text("数据库中还没有任何机器人。")
        return

    manager = context.application.bot_data['manager']
    running_tokens = manager.running_bots.keys()

    message_parts = ["<b>机器人列表:</b>\n\n"]
    for bot in all_bots:
        run_status = "✅ 在线" if bot['bot_token'] in running_tokens else "❌ 离线"

        agent_name = html.escape(bot['agent_name'])
        reg_link = html.escape(bot['registration_link'])
        # 频道链接现在可能不存在，这里可以移除或标记
        channel_link = html.escape(bot.get('channel_link') or'未配置')
        video_url = html.escape(bot['video_url'] or '未配置')
        image_url = html.escape(bot['image_url'] or '未配置')
        # 预测机器人链接已移除展示
        bot_token = html.escape(bot['bot_token'])

        part = (
            f"<b>代理:</b> {agent_name}\n"
            f"<b>状态:</b> {run_status}\n"
            f"<b>注册链接:</b> {reg_link}\n"
            f"<b>欢迎视频URL:</b> {video_url}\n"
            f"<b>付款图片URL:</b> {image_url}\n"
            f"<b>Token:</b> <code>{bot_token}</code>\n"
            f"--------------------\n"
        )
        message_parts.append(part)

    await update.message.reply_text("".join(message_parts), parse_mode='HTML')


# --- 强制触发一次发送 ---
async def send_now_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    all_bots = database.get_active_bots(role=BOT_TYPE_CHANNEL)
    if not all_bots:
        await update.message.reply_text("当前没有频道带单机器人。")
        return
    keyboard = []
    for bot in all_bots:
        keyboard.append([InlineKeyboardButton(bot['agent_name'], callback_data=f"sendnow_{bot['bot_token']}")])
    await update.message.reply_text("请选择要立即发送的频道机器人：", reply_markup=InlineKeyboardMarkup(keyboard))


async def send_now_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    token = query.data.split('_', 1)[-1]
    supervisor = context.application.bot_data.get('channel_supervisor')
    if not supervisor:
        await query.edit_message_text("发送服务未启动。")
        return
    ok = await supervisor.send_now(token)
    if ok:
        await query.edit_message_text("✅ 已触发一次发送。")
    else:
        await query.edit_message_text("❌ 触发失败（机器人可能未运行）。")


# --- 添加机器人流程 ---
async def start_add_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update): return ConversationHandler.END
    await update.message.reply_text("好的，我们来添加一个新机器人。\n请问这个代理的名称是？")
    return GETTING_AGENT_NAME


async def get_agent_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['agent_name'] = update.message.text
    await update.message.reply_text("名称已收到。\n现在，请把新机器人的`Token`发给我。")
    return GETTING_BOT_TOKEN


async def get_bot_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    token = (update.message.text or "").strip()
    if ":" not in token or not token.split(":")[0].isdigit():
        await update.message.reply_text("Token格式似乎不正确，请重新发送。")
        return GETTING_BOT_TOKEN
    context.user_data['bot_token'] = token
    
    # 新增：询问机器人类型
    keyboard = [
        [InlineKeyboardButton("私聊引导注册", callback_data=f"bottype_{BOT_TYPE_GUIDE}")],
        [InlineKeyboardButton("频道带单", callback_data=f"bottype_{BOT_TYPE_CHANNEL}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Token已收到。\n请选择这个机器人的用途类型：",
        reply_markup=reply_markup
    )
    return GETTING_BOT_TYPE


async def get_bot_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    bot_type = query.data.split('_')[1]  # bottype_private 或 bottype_channel
    context.user_data['bot_role'] = bot_type
    
    if bot_type == BOT_TYPE_GUIDE:
        # 私聊引导注册类型需要注册链接
        await query.edit_message_text("已选择【私聊引导注册】类型。\n现在，请把这个代理的专属【注册链接】发给我。")
        return GETTING_REG_LINK
    else:  # BOT_TYPE_CHANNEL
        # 频道带单类型直接跳过注册链接，只需要频道ID
        context.user_data['reg_link'] = ""  # 设置空注册链接
        await query.edit_message_text("已选择【频道带单】类型。\n现在，请输入【带单频道链接】（如 @your_channel 或 https://t.me/your_channel 或直接输入频道ID）。")
        return GETTING_CHANNEL_LINK


async def get_reg_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['reg_link'] = update.message.text
    
    # 私聊引导注册类型需要频道链接
    await update.message.reply_text("注册链接已收到。\n现在，请输入【带单频道链接】（如 @your_channel 或 https://t.me/your_channel 或直接输入频道ID）。")
    return GETTING_CHANNEL_LINK


async def get_channel_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    channel_link = (update.message.text or "").strip()
    # 允许任意文本，后续由 axibot 进行规范化处理
    context.user_data['channel_link'] = channel_link
    
    # 区分不同类型的后续流程
    if context.user_data.get('bot_role') == BOT_TYPE_GUIDE:
        # 引导类型已收集完所需信息，直接跳过游戏链接
        context.user_data['play_url'] = ""
        
        # 直接到视频URL
        keyboard = [
            [InlineKeyboardButton("跳过", callback_data="skip_video")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "频道链接已收到。\n下一步，请把欢迎视频的【公开URL链接】发给我。\n\n如果不需要，请点击【跳过】按钮。",
            reply_markup=reply_markup
        )
        return GETTING_VIDEO_URL
    else:
        # 频道类型直接进入游戏链接步骤
        await update.message.reply_text("频道链接已收到。\n请输入【游戏链接 play_url】（例如 https://xz.u7777.net/?dl=7be9v4）。")
        return GETTING_PLAY_URL


async def get_play_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['play_url'] = (update.message.text or "").strip()
    
    # 频道类型到此为止，不需要视频和图片
    if context.user_data.get('bot_role') == BOT_TYPE_CHANNEL:
        # 频道带单类型已完成所有必要配置
        context.user_data['video_url'] = None
        context.user_data['image_url'] = None
        
        name = context.user_data['agent_name']
        token = context.user_data['bot_token']
        reg_link = context.user_data['reg_link']
        play_url = context.user_data.get('play_url')
        video_url = context.user_data.get('video_url')
        image_url = context.user_data.get('image_url') 
        prediction_bot_link = None
        channel_link = context.user_data.get('channel_link') or ""
        bot_role = context.user_data.get('bot_role') or 'private'

        await update.message.reply_text("正在保存所有配置并尝试启动机器人...")
        new_bot_config = database.add_bot(name, token, reg_link, channel_link, play_url, video_url, image_url, prediction_bot_link, bot_role)

        if not new_bot_config:
            await update.message.reply_text("❌ 保存失败！这个Bot Token可能已经存在于数据库中。")
            context.user_data.clear()
            return ConversationHandler.END

        await update.message.reply_text(f"✅ 已保存为频道带单机器人 '{name}'。Axibot 将自动加载并在频道发送消息。")

        context.user_data.clear()
        return ConversationHandler.END
    
    # 私聊引导类型继续收集媒体
    keyboard = [
        [InlineKeyboardButton("跳过", callback_data="skip_video")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "play_url 已收到。\n下一步，请把欢迎视频的【公开URL链接】发给我。\n\n如果不需要，请点击【跳过】按钮。",
        reply_markup=reply_markup
    )
    return GETTING_VIDEO_URL


async def get_url_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # 处理回调查询（按钮点击）和文本消息两种情况
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if query.data == "skip_video":
            context.user_data['video_url'] = None
            keyboard = [
                [InlineKeyboardButton("跳过", callback_data="skip_image")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "已跳过视频配置。\n最后，请把用于提示用户充值的【图片公开URL】发给我。\n\n如果不需要，请点击【跳过】按钮。",
                reply_markup=reply_markup
            )
        return GETTING_IMAGE_URL
    
    # 文本消息处理
    url_input = update.message.text
    if url_input and url_input.lower() in ["跳过", "skip"]:
        context.user_data['video_url'] = None
        keyboard = [
            [InlineKeyboardButton("跳过", callback_data="skip_image")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "好的，已跳过视频配置。\n最后，请把用于提示用户充值的【图片公开URL】发给我。\n\n如果不需要，请点击【跳过】按钮。",
            reply_markup=reply_markup
        )
    else:
        context.user_data['video_url'] = url_input
        keyboard = [
            [InlineKeyboardButton("跳过", callback_data="skip_image")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
            "视频URL已收到。\n最后，请把用于提示用户充值的【图片公开URL】发给我。\n\n如果不需要，请点击【跳过】按钮。",
            reply_markup=reply_markup
        )
    return GETTING_IMAGE_URL


async def get_image_url_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # 处理回调查询（按钮点击）和文本消息两种情况
    image_url = None
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
        if query.data == "skip_image":
            await query.edit_message_text("好的，已跳过图片配置。")
        else:
            await query.edit_message_text("收到无效选项，已默认跳过图片配置。")
    else:
        chat_id = update.message.chat_id
        url_input = update.message.text
        if url_input and url_input.lower() in ["跳过", "skip"]:
            await context.bot.send_message(chat_id=chat_id, text="好的，已跳过图片配置。")
        else:
            image_url = url_input
            await context.bot.send_message(chat_id=chat_id, text="✅ 图片链接已收到。")

    name = context.user_data['agent_name']
    token = context.user_data['bot_token']
    reg_link = context.user_data['reg_link']
    play_url = context.user_data.get('play_url')
    video_url = context.user_data.get('video_url')
    prediction_bot_link = None
    channel_link = context.user_data.get('channel_link') or ""
    bot_role = context.user_data.get('bot_role') or 'private'

    await context.bot.send_message(chat_id=chat_id, text="正在保存所有配置并尝试启动机器人...")
    new_bot_config = database.add_bot(name, token, reg_link, channel_link, play_url, video_url, image_url, prediction_bot_link, bot_role)

    if not new_bot_config:
        await context.bot.send_message(chat_id=chat_id, text="❌ 保存失败！这个Bot Token可能已经存在于数据库中。")
        context.user_data.clear()
        return ConversationHandler.END

    try:
        # 私聊引导机器人
        manager = context.application.bot_data['manager']
        await manager.start_agent_bot(new_bot_config)

        # 若为频道带单：交给 ChannelSupervisor 动态启动；不自动发
        if bot_role == BOT_TYPE_CHANNEL:
            supervisor = context.application.bot_data.get('channel_supervisor')
            if supervisor is not None:
                await supervisor.start(new_bot_config)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ 成功！代理 '{name}' 的机器人已添加并上线。")
    except Exception as e:
        logger.error(f"动态启动机器人失败: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"数据库已保存，但动态启动失败。请检查日志。")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_add_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("操作已取消。")
    context.user_data.clear()
    return ConversationHandler.END


add_bot_handler = ConversationHandler(
    entry_points=[CommandHandler("addbot", start_add_bot)],
    states={
        GETTING_AGENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_agent_name)],
        GETTING_BOT_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_bot_token)],
        GETTING_BOT_TYPE: [CallbackQueryHandler(get_bot_type, pattern="^bottype_")],
        GETTING_REG_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reg_link)],
        GETTING_CHANNEL_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_channel_link)],
        GETTING_PLAY_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_play_url)],
        GETTING_VIDEO_URL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_url_and_save),
            CallbackQueryHandler(get_url_and_save, pattern="^skip_video$")
        ],
        GETTING_IMAGE_URL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_image_url_and_save),
            CallbackQueryHandler(get_image_url_and_save, pattern="^skip_image$")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_add_bot)],
)


# --- 删除机器人流程 (保持不变) ---
async def delete_bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    all_bots = database.get_all_bots()
    if not all_bots:
        await update.message.reply_text("数据库中还没有任何机器人可以删除。")
        return
    keyboard = []
    for bot in all_bots:
        # 使用数据库自增 id 作为回调参数，避免 Token 过长或包含冒号导致平台截断
        bot_id = bot.get('id') if isinstance(bot, dict) else bot.id
        button = InlineKeyboardButton(bot['agent_name'], callback_data=f"delbot_confirm_{bot_id}")
        keyboard.append([button])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("请选择您要删除的代理机器人：", reply_markup=reply_markup)


async def delete_bot_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_ref = query.data.split('_')[-1]
    bot_config = None
    # 优先按 id 解析；失败则回退按 token
    try:
        bot_id = int(bot_ref)
        bot_config = database.get_bot_by_id(bot_id)
    except ValueError:
        bot_config = database.get_bot_by_token(bot_ref)
    if not bot_config:
        await query.edit_message_text("错误：找不到该机器人，可能已被删除。")
        return
    # 回调继续携带 id；若当前只有 token 则携带 token
    confirm_ref = str(bot_config.get('id')) if bot_config and bot_config.get('id') is not None else bot_ref
    keyboard = [[
        InlineKeyboardButton("✅ 是的，立即删除", callback_data=f"delbot_execute_{confirm_ref}"),
        InlineKeyboardButton("❌ 取消", callback_data="delbot_cancel")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"⚠️ <b>严重警告</b> ⚠️\n\n您确定要删除代理 <b>{html.escape(bot_config['agent_name'])}</b> 吗？\n此操作将：\n1. <b>立即停止</b>该机器人的运行。\n2. 从数据库中<b>永久删除</b>其所有配置和用户数据。\n\n<b>此操作无法撤销！</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def delete_bot_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_ref = query.data.split('_')[-1]
    # 兼容老按钮：优先按 id，失败则按 token
    bot_config = None
    bot_id = None
    try:
        bot_id = int(bot_ref)
        bot_config = database.get_bot_by_id(bot_id)
    except ValueError:
        bot_config = database.get_bot_by_token(bot_ref)
    agent_name = html.escape(bot_config['agent_name']) if bot_config else "未知"
    await query.edit_message_text(f"正在停止机器人 '{agent_name}'...")
    manager = context.application.bot_data['manager']
    if bot_config and bot_config.get('bot_token'):
        await manager.stop_agent_bot(bot_config['bot_token'])
        # 若为频道带单，同时停止对应频道发送端
        supervisor = context.application.bot_data.get('channel_supervisor')
        if supervisor is not None:
            try:
                await supervisor.stop(bot_config['bot_token'])
            except Exception:
                pass
    await query.edit_message_text(f"正在从数据库中删除 '{agent_name}'...")
    success = False
    if bot_config:
        if bot_id is not None:
            success = database.delete_bot_by_id(bot_id)
        else:
            success = database.delete_bot(bot_config['bot_token'])
    if success:
        await query.edit_message_text(f"✅ 代理机器人 '{agent_name}' 已被成功删除。")
    else:
        await query.edit_message_text("❌ 删除失败！数据库中未找到相应机器人。")


async def delete_bot_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("操作已取消。")