import asyncio
import logging
import random
import platform
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, ApplicationBuilder

import config

# --- 日志和常量配置 (不变) ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

PROBABILITY_PER_MINUTE = 50 / (24 * 60)
GRID_SIZE = 6
TOTAL_CELLS = GRID_SIZE * GRID_SIZE
STAR_EMOJI = "⭐️"
SQUARE_EMOJI = "🟦"


# --- 机器人核心功能 ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    await update.message.reply_text(
        "我破解了这款Mines 游戏，结果预测准确率在97% 以上。\n准备好了吗？跟上我的脚步吧！"
    )


def generate_signal_message() -> str:
    # ... 此函数不变 ...
    pass


# --- 倒计时消息的回调函数 ---
async def send_5_min_warning(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text="💎💎💎还剩5分钟💎💎💎")


async def send_3_min_warning(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text="💎💎💎还剩3分钟💎💎💎")


async def send_1_min_warning(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text="💎💎💎还剩1分钟💎💎💎")


async def send_success_and_unlock(context: ContextTypes.DEFAULT_TYPE):
    """发送最终成功消息，并解锁信号"""
    await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text="✅ ✅ ✅ 避雷成功啦 ✅ ✅ ✅")
    # --- 关键修改：解锁信号 ---
    context.bot_data['is_signal_active'] = False
    logger.info("信号已结束，锁已解除。")


async def send_signal(context: ContextTypes.DEFAULT_TYPE):
    """
    发送完整信号流，并管理信号锁。
    """
    # --- 关键修改：发送前检查锁 ---
    if context.bot_data.get('is_signal_active', False):
        logger.info("检测到已有信号正在进行中，本次跳过。")
        return

    try:
        # --- 关键修改：立即加锁 ---
        context.bot_data['is_signal_active'] = True
        logger.info("信号锁已激活，准备发送新信号...")

        await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text="正在检查新的信号。")

        await asyncio.sleep(random.uniform(3, 5))

        signal_message = generate_signal_message()
        await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text=signal_message)
        logger.info(f"成功发送一条信号到 {config.TARGET_CHAT_ID}")

        job_queue = context.job_queue
        job_queue.run_once(send_5_min_warning, 3)
        job_queue.run_once(send_3_min_warning, 120)
        job_queue.run_once(send_1_min_warning, 240)
        # --- 关键修改：最后一个任务负责解锁 ---
        job_queue.run_once(send_success_and_unlock, 300)

    except Exception as e:
        logger.error(f"发送信号到 {config.TARGET_CHAT_ID} 失败: {e}")
        # 即使失败也要解锁，避免永久锁定
        context.bot_data['is_signal_active'] = False


async def schedule_checker(context: ContextTypes.DEFAULT_TYPE):
    """每分钟被调用一次，根据概率决定是否发送信号"""
    if random.random() < PROBABILITY_PER_MINUTE:
        asyncio.create_task(send_signal(context))

async def test_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /testsignal 命令，立即发送一条信号用于测试"""
    await update.message.reply_text("好的，正在发送一条包含完整倒计时的测试信号到目标频道/群组...")
    asyncio.create_task(send_signal(context))
    logger.info(f"收到测试指令，由用户 {update.effective_user.id} 触发。")


# --- 核心启动与关闭逻辑 ---
async def startup():
    logger.info("机器人启动中...")

    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # 注册指令处理器
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testsignal", test_signal))

    # 安排重复性任务
    job_queue = app.job_queue
    job_queue.run_repeating(schedule_checker, interval=60, first=10)

    # 非阻塞模式启动
    await app.initialize()
    await app.updater.start_polling()
    await app.start()

    logger.info("机器人已启动，并开始监控信号。")
    return app


async def shutdown(app: Application):
    logger.info("正在关闭机器人...")
    if app.updater and app.updater._running:
        await app.updater.stop()
    await app.stop()
    await app.shutdown()
    logger.info("机器人已关闭。")


# --- 程序主入口 (不变) ---
if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.get_event_loop()
    application = None

    try:
        application = loop.run_until_complete(startup())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("检测到手动中断 (Ctrl+C)，开始优雅关闭...")
    finally:
        if application:
            loop.run_until_complete(shutdown(application))
        logger.info("程序已完全关闭。")
