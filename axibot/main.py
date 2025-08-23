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

PROBABILITY_PER_MINUTE =1500 / (24 * 60)
GRID_SIZE_U = 6
GRID_SIZE_D = 5
TOTAL_CELLS = GRID_SIZE_U * GRID_SIZE_D
STAR_EMOJI = "⭐️"
SQUARE_EMOJI = "🟦"


# --- 机器人核心功能 ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    await update.message.reply_text(
        "我破解了这款Mines 游戏，结果预测准确率在97% 以上。\n准备好了吗？跟上我的脚步吧！"
    )


def generate_signal_message() -> str:
    """生成一条完整的信号消息"""
    mines_count = random.randint(3, 6)
    attempts_count = random.randint(4, 8)

    grid = [STAR_EMOJI] * attempts_count + [SQUARE_EMOJI] * (TOTAL_CELLS - attempts_count)
    random.shuffle(grid)

    grid_text = ""
    for i, emoji in enumerate(grid):
        grid_text += emoji
        if (i + 1) % GRID_SIZE_U == 0:
            grid_text += "\n"

    signal_text = (
        f"确认入场！\n"
        f"地雷数：{mines_count}\n"
        f"尝试数：{attempts_count}\n"
        f"有效时间：5分钟\n\n"
        f"立即游戏 (www.baidu.com)\n\n"
        f"{grid_text}"
    )
    return signal_text


# --- 新增：倒计时消息的回调函数 ---

async def send_5_min_warning(context: ContextTypes.DEFAULT_TYPE):
    """发送 5 分钟剩余提示"""
    await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text="💎💎💎还剩5分钟💎💎💎")


async def send_3_min_warning(context: ContextTypes.DEFAULT_TYPE):
    """发送 3 分钟剩余提示"""
    await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text="💎💎💎还剩3分钟💎💎💎")


async def send_1_min_warning(context: ContextTypes.DEFAULT_TYPE):
    """发送 1 分钟剩余提示"""
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
    新增逻辑：每3次调用才发送一次前置图片消息。
    """
    # --- 关键修改：发送前检查锁 ---
    if context.bot_data.get('is_signal_active', False):
        logger.info("检测到已有信号正在进行中，本次跳过。")
        return

    try:
        # --- 关键修改：初始化并更新调用计数器 ---
        call_count = context.bot_data.get('signal_call_count', 0) + 1
        context.bot_data['signal_call_count'] = call_count
        logger.info(f"信号任务被触发，这是第 {call_count} 次。")

        # --- 关键修改：判断是否为第3次调用，并发送图片 ---
        if call_count % 3 == 1:
            logger.info("满足3次触发条件，准备发送图片消息。")
            # 从config中随机选择一张图片
            image_url = random.choice(config.IMAGE_LIBRARY['firstdd'])
            # 您可以自定义这里的文案
            caption_text = "\n✨ 现在，就跟随我的脚步，踏入这场全新的游戏冒险！\n凭借前沿智能技术，它将带来前所未有的激情与挑战。\n\n🎮 准备好了吗？Mines 游戏即将为你开启全新的感官旅程.\n只需轻松几步，就能快速上手，畅享刺激爽快、惊喜不断的娱乐体验！"

            try:
                await context.bot.send_photo(
                    chat_id=config.TARGET_CHAT_ID,
                    photo=image_url,
                    caption=caption_text
                )
                logger.info(f"成功发送图片消息到 {config.TARGET_CHAT_ID}")
                # 发送图片后可以稍微等待一下，让用户有时间看
                await asyncio.sleep(random.uniform(2, 4))

            except Exception as e:
                logger.error(f"发送图片消息失败: {e}")
                # 即使图片发送失败，我们也可以选择继续发送主信号

        # --- 关键修改：立即加锁 ---
        context.bot_data['is_signal_active'] = True
        logger.info("信号锁已激活，准备发送新信号...")

        await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text="正在检查新的信号。")

        await asyncio.sleep(random.uniform(3, 5))

        signal_message = generate_signal_message()
        await context.bot.send_message(chat_id=config.TARGET_CHAT_ID, text=signal_message)
        logger.info(f"成功发送一条信号到 {config.TARGET_CHAT_ID}")

        job_queue = context.job_queue
        # 倒计时时间也可以根据需要调整
        job_queue.run_once(send_5_min_warning, 3)  # 为了测试方便，这里依然是秒
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
    """处理 /testsignal 命令，用于测试（同样会遵守锁机制）"""
    await update.message.reply_text("好的，正在尝试发送一条测试信号（如果当前无信号正在进行）...")
    asyncio.create_task(send_signal(context))
    logger.info(f"收到测试指令，由用户 {update.effective_user.id} 触发。")


# --- 核心启动与关闭逻辑 (不变) ---
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
