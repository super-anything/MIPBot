import logging
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
)

import config
import database
logger = logging.getLogger(__name__)

# --- 对话状态定义 ---
# 移除了 GETTING_CHANNEL_LINK
GETTING_AGENT_NAME, GETTING_BOT_TOKEN, GETTING_REG_LINK, GETTING_VIDEO_URL, GETTING_PREDICTION_LINK, GETTING_IMAGE_URL = range(
    10, 16)


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
        pred_link = html.escape(bot['prediction_bot_link'] or '未配置')
        bot_token = html.escape(bot['bot_token'])

        part = (
            f"<b>代理:</b> {agent_name}\n"
            f"<b>状态:</b> {run_status}\n"
            f"<b>注册链接:</b> {reg_link}\n"
            f"<b>欢迎视频URL:</b> {video_url}\n"
            f"<b>付款图片URL:</b> {image_url}\n"
            f"<b>预测机器人链接:</b> {pred_link}\n"
            f"<b>Token:</b> <code>{bot_token}</code>\n"
            f"--------------------\n"
        )
        message_parts.append(part)

    await update.message.reply_text("".join(message_parts), parse_mode='HTML')


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
    token = update.message.text
    if ":" not in token or not token.split(":")[0].isdigit():
        await update.message.reply_text("Token格式似乎不正确，请重新发送。")
        return GETTING_BOT_TOKEN
    context.user_data['bot_token'] = token
    await update.message.reply_text("Token已收到。\n现在，请把这个代理的专属【注册链接】发给我。")
    return GETTING_REG_LINK


async def get_reg_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['reg_link'] = update.message.text
    # 删除了 GETTING_CHANNEL_LINK，直接跳到 GETTING_VIDEO_URL
    await update.message.reply_text(
        "注册链接已收到。\n下一步，请把欢迎视频的【公开URL链接】发给我。\n\n如果不需要，请直接回复 `跳过`")
    return GETTING_VIDEO_URL


# get_channel_link 函数已被移除


async def get_url_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url_input = update.message.text
    if url_input.lower() in ["跳过", "skip"]:
        context.user_data['video_url'] = None
        await update.message.reply_text("好的，已跳过欢迎视频配置。\n现在，请输入【带单频道链接】。")
    else:
        context.user_data['video_url'] = url_input
        await update.message.reply_text("视频URL已收到。\n现在，请输入【带单频道链接】。")

    return GETTING_PREDICTION_LINK


# --- 关键修改：移除了所有输入验证 ---
async def get_prediction_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # 移除了所有验证，直接接受用户输入的任何文本
    context.user_data['prediction_bot_link'] = update.message.text
    await update.message.reply_text(
        "预测机器人链接已收到。\n最后，请把用于提示用户充值的【图片的公开URL链接】发给我。\n\n如果不需要，请回复 `跳过`。")

    return GETTING_IMAGE_URL


async def get_image_url_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    image_url = None
    url_input = update.message.text
    if url_input.lower() in ["跳过", "skip"]:
        await update.message.reply_text("好的，已跳过图片配置。")
    else:
        image_url = url_input
        await update.message.reply_text("✅ 图片链接已收到。")

    name = context.user_data['agent_name']
    token = context.user_data['bot_token']
    reg_link = context.user_data['reg_link']
    video_url = context.user_data['video_url']
    prediction_bot_link = context.user_data['prediction_bot_link']
    # 频道链接现在设置为 None 或空字符串，取决于数据库设计
    channel_link = "" # 或者

    await update.message.reply_text("正在保存所有配置并尝试启动机器人...")
    new_bot_config = database.add_bot(name, token, reg_link, channel_link, video_url, image_url, prediction_bot_link)

    if not new_bot_config:
        await update.message.reply_text("❌ 保存失败！这个Bot Token可能已经存在于数据库中。")
        context.user_data.clear()
        return ConversationHandler.END

    try:
        manager = context.application.bot_data['manager']
        await manager.start_agent_bot(new_bot_config)
        await update.message.reply_text(f"✅ 成功！代理 ‘{name}’ 的机器人已添加并在线运行！")
    except Exception as e:
        logger.error(f"动态启动机器人失败: {e}")
        await update.message.reply_text(f"数据库已保存，但机器人动态启动失败。请检查日志。")

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
        GETTING_REG_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reg_link)],
        # 移除了 GETTING_CHANNEL_LINK 的处理器
        GETTING_VIDEO_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_url_and_save)],
        GETTING_PREDICTION_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prediction_link)],
        GETTING_IMAGE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_image_url_and_save)],
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
        button = InlineKeyboardButton(bot['agent_name'], callback_data=f"delbot_confirm_{bot['bot_token']}")
        keyboard.append([button])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("请选择您要删除的代理机器人：", reply_markup=reply_markup)


async def delete_bot_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    token = query.data.split('_')[-1]
    bot_config = database.get_bot_by_token(token)
    if not bot_config:
        await query.edit_message_text("错误：找不到该机器人，可能已被删除。")
        return
    keyboard = [[
        InlineKeyboardButton("✅ 是的，立即删除", callback_data=f"delbot_execute_{token}"),
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
    token = query.data.split('_')[-1]
    bot_config = database.get_bot_by_token(token)
    agent_name = html.escape(bot_config['agent_name']) if bot_config else "未知"
    await query.edit_message_text(f"正在停止机器人 '{agent_name}'...")
    manager = context.application.bot_data['manager']
    await manager.stop_agent_bot(token)
    await query.edit_message_text(f"正在从数据库中删除 '{agent_name}'...")
    success = database.delete_bot(token)
    if success:
        await query.edit_message_text(f"✅ 代理机器人 '{agent_name}' 已被成功删除。")
    else:
        await query.edit_message_text(f"❌ 删除失败！在数据库中找不到Token为该值的机器人。")


async def delete_bot_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("操作已取消。")
