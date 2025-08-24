import asyncio
import logging
import platform,random
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, ApplicationBuilder, CallbackQueryHandler

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
    delete_bot_cancel
)
from .channel_supervisor import ChannelSupervisor
from .handlers import conversation_handler

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
        token = bot_config['bot_token']
        name = bot_config['agent_name']

        if token in self.running_bots:
            logger.warning(f"机器人 '{name}' 已在运行中。")
            return

        try:
            agent_app = ApplicationBuilder().token(token).build()
            agent_app.bot_data['config'] = bot_config

            # --- 关键修改：加载总对话处理器 ---
            agent_app.add_handler(conversation_handler)

            await agent_app.initialize()
            await agent_app.updater.start_polling()
            await agent_app.start()

            self.running_bots[token] = agent_app
            logger.info(f"代理机器人 '{name}' 已成功启动并开始轮询。")
        except Exception as e:
            logger.error(f"代理机器人 '{name}' ({token}) 启动时出现错误: {e}")

    async def stop_agent_bot(self, token: str):
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
        # 仅启动私聊引导机器人
        initial_bots = database.get_active_bots(role='private')
        logger.info(f"发现 {len(initial_bots)} 个活跃的代理机器人，正在启动...")
        tasks = [self.start_agent_bot(bot_config) for bot_config in initial_bots]
        await asyncio.gather(*tasks)


# --- 4. 核心启动与关闭函数的定义 ---
async def startup():
    database.initialize_db()
    manager = BotManager()
    axi_manager = AxiBotManager() if AxiBotManager is not None else None
    channel_supervisor = ChannelSupervisor()

    # --- 关键修改：优化了管理员菜单 ---
    bot_commands = [
        BotCommand("addbot", "➕ 添加新代理"),
        BotCommand("listbots", "📋 查看列表"),
        BotCommand("sendnow", "🚀 频道立即发送"),
        BotCommand("delbot", "🗑️ 删除代理"),
        BotCommand("help", "❓ 获取帮助"),
        BotCommand("cancel", "❌ 取消当前操作"),
    ]

    async def post_init(application: Application):
        await application.bot.set_my_commands(bot_commands)

    admin_app = ApplicationBuilder().token(config.ADMIN_BOT_TOKEN).post_init(post_init).build()
    admin_app.bot_data['manager'] = manager
    if axi_manager is not None:
        admin_app.bot_data['axi_manager'] = axi_manager
    admin_app.bot_data['channel_supervisor'] = channel_supervisor

    # 注册所有管理员处理器
    admin_app.add_handler(CommandHandler(["start", "help"], start_admin))
    admin_app.add_handler(add_bot_handler)
    admin_app.add_handler(CommandHandler("listbots", list_bots))
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
    # 启动频道发送管理器并开始监控（无需单独进程）
    if axi_manager is not None:
        await axi_manager.start_all_bots()
        axi_manager.start_monitor()

    logger.info("正在以非阻塞模式启动主管理机器人...")
    await admin_app.initialize()
    await admin_app.updater.start_polling()
    await admin_app.start()

    logger.info("所有机器人均已运行。按 Ctrl+C 退出。")

    return manager, admin_app


async def shutdown(manager: BotManager, admin_app: Application):
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
