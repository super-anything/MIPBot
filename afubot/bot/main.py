"""afubot 主入口

职责：
- 初始化数据库与后台管理员机器人
- 启动私聊引导型代理机器人（`BotManager`）
- 启动并托管频道带单型机器人（`ChannelSupervisor`）
- 提供优雅的启动/关闭流程
"""

import asyncio
import logging
import platform,random
from pathlib import Path
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ApplicationBuilder, CallbackQueryHandler, PicklePersistence, ContextTypes
from telegram.request import HTTPXRequest

# 引入频道发送管理器
try:
    from axibot.main import AxiBotManager
except Exception:
    AxiBotManager = None
from . import config
from . import database
from .admin_handlers import (
    add_bot_handler,
    start_admin,
    list_bots,
    send_now_start,
    send_now_execute,
    delete_bot_start,
    delete_bot_confirm,
    delete_bot_execute,
    delete_bot_cancel,
    edit_play_handler,
    edit_reg_handler
)
from .channel_supervisor import ChannelSupervisor
from .handlers import conversation_handler, nag_recharge_callback, NAG_INTERVAL_SECONDS

# --- 2. 日志配置 ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# --- 3. BotManager 类的定义 ---
class BotManager:
    def __init__(self):
        self.running_bots = {}

    async def start_agent_bot(self, bot_config: dict):
        """按配置启动一个私聊引导机器人，并带持久化恢复。

        - 使用 `PicklePersistence` 进行对话持久化
        - 将 `conversation_handler` 挂载到子应用
        - 重启后恢复未完成的会话提醒/阶段
        """
        token = bot_config['bot_token']
        name = bot_config['agent_name']

        if token in self.running_bots:
            logger.warning(f"机器人 '{name}' 已在运行中。")
            return

        try:
            request = HTTPXRequest(connection_pool_size=100)
            # 为每个机器人启用基于文件的持久化，避免重启导致会话中断
            persist_dir = Path(__file__).resolve().parent / 'persist'
            persist_dir.mkdir(parents=True, exist_ok=True)
            persist_file = persist_dir / f"conv_{token.split(':')[0]}.bin"
            persistence = PicklePersistence(filepath=str(persist_file))
            agent_app = ApplicationBuilder().token(token).request(request).persistence(persistence).build()
            # 仅日志的全局错误处理器
            async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
                logger.exception("Unhandled exception in agent_app", exc_info=context.error)
            agent_app.add_error_handler(_on_error)
            agent_app.bot_data['config'] = bot_config
            # 确保运行期也能根据 token 从数据库回源
            try:
                agent_app.bot_data['config']['bot_token'] = token
            except Exception:
                pass

            # --- 关键修改：加载总对话处理器 ---
            agent_app.add_handler(conversation_handler)

            await agent_app.initialize()
            logger.info(f"代理机器人 '{name}' initialize 完成，准备启动应用…")
            await agent_app.start()
            logger.info(f"代理机器人 '{name}' start 完成，开启轮询…")
            # 私聊引导：不丢弃待处理更新，减少重启窗口期间用户点击丢失
            await agent_app.updater.start_polling(drop_pending_updates=False)

            self.running_bots[token] = agent_app
            logger.info(f"代理机器人 '{name}' 已成功启动并开始轮询。")

            # --- 重启后自动恢复未完成对话到相应阶段，并继续发送提示/按钮 ---
            async def resume_conversations():
                try:
                    sessions = database.list_user_conversations(token) or []
                    for row in sessions:
                        # row 兼容 MySQL(dict) 与 SQLite(dict)
                        chat_id = row.get('chat_id') if isinstance(row, dict) else row[0]
                        state = row.get('state') if isinstance(row, dict) else row[1]
                        try:
                            if state == 'AWAITING_REGISTER_CONFIRM':
                                # 避免重复补发按钮，由用户点击旧按钮继续
                                pass
                            elif state == 'AWAITING_ID':
                                # 避免重复提示，必要时由用户输入触发
                                pass
                            elif state == 'AWAITING_RECHARGE_CONFIRM':
                                # 重新安排提醒任务
                                job_name = f"recharge_nag_{chat_id}_{chat_id}"
                                agent_app.job_queue.run_once(
                                    nag_recharge_callback,
                                    NAG_INTERVAL_SECONDS,
                                    chat_id=chat_id,
                                    user_id=chat_id,
                                    name=job_name
                                )
                                # 初始化 user_data 以便后续取消任务
                                try:
                                    agent_app.user_data[chat_id]['recharge_nag_attempts'] = 0
                                    agent_app.user_data[chat_id][f'recharge_nag_job_name_{chat_id}'] = job_name
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.warning(f"恢复会话到 {state} 阶段失败 chat_id={chat_id}: {e}")
                except Exception as e:
                    logger.error(f"恢复该机器人会话时出错: {e}")

            agent_app.create_task(resume_conversations())
        except Exception as e:
            logger.error(f"代理机器人 '{name}' ({token}) 启动时出现错误: {e}")

    async def stop_agent_bot(self, token: str):
        """停止并清理一个正在运行的私聊引导机器人。"""
        if token in self.running_bots:
            app = self.running_bots[token]
            name = app.bot_data.get('config', {}).get('agent_name', '未知')
            try:
                if app.updater and app.updater._running:
                    await app.updater.stop()
                await app.stop()
                await app.shutdown()
                del self.running_bots[token]
                logger.info(f"机器人 '{name}' 已被成功停止。")
            except Exception as e:
                logger.error(f"停止机器人 '{name}' 时发生错误: {e}")

    async def start_initial_bots(self):
        """从数据库批量启动所有活跃的私聊引导机器人。"""
        # 仅启动私聊引导机器人
        initial_bots = database.get_active_bots(role='private')
        logger.info(f"发现 {len(initial_bots)} 个活跃的代理机器人，正在启动...")
        tasks = [self.start_agent_bot(bot_config) for bot_config in initial_bots]
        await asyncio.gather(*tasks)


# --- 4. 核心启动与关闭函数的定义 ---
async def startup():
    """系统启动：初始化 DB、管理员应用、并启动各类机器人。"""
    database.initialize_db()
    manager = BotManager()
    # 不再启用 AxiBotManager，统一由 ChannelSupervisor 管理频道机器人，避免重复实例
    axi_manager = None
    channel_supervisor = ChannelSupervisor()

    # --- 关键修改：优化了管理员菜单 ---
    bot_commands = [
        BotCommand("addbot", "➕ 添加新代理"),
        BotCommand("listbots", "📋 查看列表"),
        BotCommand("sendnow", "🚀 频道立即发送"),
        BotCommand("delbot", "🗑️ 删除代理"),
        BotCommand("editplay", "✏️ 修改频道游戏链接"),
        BotCommand("editreg", "✏️ 修改引导注册链接"),
        BotCommand("help", "❓ 获取帮助"),
        BotCommand("cancel", "❌ 取消当前操作"),
    ]

    async def post_init(application: Application):
        await application.bot.set_my_commands(bot_commands)

    admin_app = ApplicationBuilder().token(config.ADMIN_BOT_TOKEN).post_init(post_init).build()
    # 仅日志的全局错误处理器
    async def _on_error_admin(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled exception in admin_app", exc_info=context.error)
    admin_app.add_error_handler(_on_error_admin)
    admin_app.bot_data['manager'] = manager
    admin_app.bot_data['channel_supervisor'] = channel_supervisor

    # 注册所有管理员处理器
    admin_app.add_handler(CommandHandler(["start", "help"], start_admin))
    admin_app.add_handler(add_bot_handler)
    admin_app.add_handler(edit_play_handler)
    admin_app.add_handler(edit_reg_handler)
    admin_app.add_handler(CommandHandler("listbots", list_bots))
    admin_app.add_handler(CommandHandler("catuser", __import__('afubot.bot.admin_handlers', fromlist=['catuser']).catuser))
    # 下线：认领历史机器人功能
    # admin_app.add_handler(CommandHandler("claimbot", __import__('afubot.bot.admin_handlers', fromlist=['claimbot']).claimbot))
    # admin_app.add_handler(CallbackQueryHandler(__import__('afubot.bot.admin_handlers', fromlist=['claimbot_cb']).claimbot_cb, pattern="^claimbot_ref_"))
    admin_app.add_handler(CommandHandler("sendnow", send_now_start))
    admin_app.add_handler(CommandHandler("delbot", delete_bot_start))
    admin_app.add_handler(CallbackQueryHandler(send_now_execute, pattern="^sendnow_"))
    # 兼容老格式（token）与新格式（id）：先尝试严格匹配 id（数字），再兜底
    admin_app.add_handler(CallbackQueryHandler(delete_bot_confirm, pattern="^delbot_confirm_\\d+$"))
    admin_app.add_handler(CallbackQueryHandler(delete_bot_confirm, pattern="^delbot_confirm_.+$"))
    admin_app.add_handler(CallbackQueryHandler(delete_bot_execute, pattern="^delbot_execute_\\d+$"))
    admin_app.add_handler(CallbackQueryHandler(delete_bot_execute, pattern="^delbot_execute_.+$"))
    admin_app.add_handler(CallbackQueryHandler(delete_bot_cancel, pattern="^delbot_cancel$"))

    await manager.start_initial_bots()
    # 启动已存在的频道机器人，统一由 ChannelSupervisor 管理，避免与其它服务冲突
    try:
        for bot in database.get_active_bots(role='channel'):
            await channel_supervisor.start(bot)
    except Exception as e:
        logger.error(f"启动已存在的频道机器人失败: {e}")

    logger.info("正在以非阻塞模式启动主管理机器人...")
    await admin_app.initialize()
    await admin_app.updater.start_polling(drop_pending_updates=True)
    await admin_app.start()

    logger.info("所有机器人均已运行。按 Ctrl+C 退出。")

    return manager, admin_app


async def shutdown(manager: BotManager, admin_app: Application):
    """系统优雅关闭：停止管理员应用与所有子机器人。"""
    logger.info("正在关闭主管理机器人...")
    if admin_app.updater and admin_app.updater._running:
        await admin_app.updater.stop()
    await admin_app.stop()
    await admin_app.shutdown()

    logger.info("正在关闭所有代理机器人...")
    shutdown_tasks = [manager.stop_agent_bot(token) for token in list(manager.running_bots.keys())]
    await asyncio.gather(*shutdown_tasks)


# --- 5. 程序主入口 ---
if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.get_event_loop()
    manager_instance = None
    admin_app_instance = None

    try:
        manager_instance, admin_app_instance = loop.run_until_complete(startup())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("检测到手动中断 (Ctrl+C)，开始优雅关闭...")
    finally:
        if manager_instance and admin_app_instance:
            loop.run_until_complete(shutdown(manager_instance, admin_app_instance))
        logger.info("程序已完全关闭。")
