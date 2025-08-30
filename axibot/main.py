"""axibot 频道发送子系统

职责：
- 生成频道带单信号文本与倒计时提醒
- 创建并管理单个频道发送 `Application`
- 提供 `AxiBotManager` 以批量启动、监控、暂停/恢复与权限检查

该模块也被 `afubot` 的 `ChannelSupervisor` 复用，以统一频道发送能力。
"""

import asyncio
import logging
import random
import platform
import sys
import time
import threading
import datetime
from urllib.parse import urlparse
from params import tgs_file,image_file
from telegram.ext import Application, ContextTypes, ApplicationBuilder
from telegram.error import Forbidden, BadRequest
from telegram.request import HTTPXRequest
from axibot import config


# --- 日志和常量配置 ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

PROBABILITY_PER_MINUTE = 10 / (24 * 60)
GRID_SIZE_U = 6
GRID_SIZE_D = 5
TOTAL_CELLS = GRID_SIZE_U * GRID_SIZE_D
STAR_EMOJI = "⭐️"
SQUARE_EMOJI = "🟦"


# --- 引入 afubot 数据库，跨包安全导入 ---
try:
    # 确保项目根目录在 sys.path 中
    # 便于从 axibot 运行时也能导入 afubot
    from pathlib import Path
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from afubot.bot import database as afu_db
except Exception as e:
    afu_db = None
    logger.warning(f"无法导入 afubot.bot.database，只有单频道旧模式可用: {e}")


def _normalize_channel_link(channel_link: str | None) -> str | None:
    """归一化频道链接/ID：支持 -100 前缀 ID、@用户名、t.me 链接或原样返回。"""
    if not channel_link:
        return None
    text = channel_link.strip()
    # 如果是纯数字的频道ID（常见以-100开头），转换为 int，减少 API 兼容性问题
    try:
        if text.startswith("-100") and text[1:].isdigit():
            return int(text)
    except Exception:
        pass
    if text.startswith("@"):
        return text
    if text.startswith("https://") or text.startswith("http://"):
        try:
            parsed = urlparse(text)
            if parsed.netloc in ("t.me", "telegram.me") and parsed.path:
                name = parsed.path.strip("/")
                if name:
                    return f"@{name}"
        except Exception:
            return None
    return text


def generate_signal_message(bot_config: dict | None = None) -> str:
    """生成一条（可按机器人配置定制的）信号消息。"""
    mines_count = random.randint(3, 6)
    attempts_count = random.randint(4, 8)

    grid = [STAR_EMOJI] * attempts_count + [SQUARE_EMOJI] * (TOTAL_CELLS - attempts_count)
    random.shuffle(grid)

    grid_text = ""
    for i, emoji in enumerate(grid):
        grid_text += emoji
        if (i + 1) % GRID_SIZE_U == 0:
            grid_text += "\n"

    play_url = None
    if bot_config:
        # 优先使用频道配置的 play_url；若无则回退至注册链接
        play_url = bot_config.get('play_url') or bot_config.get('registration_link')
    if not play_url:
        # 默认跳转
        play_url = "https://xz.u7777.net/"

    agent_name = (bot_config.get('agent_name') if bot_config else None) or "Agent"

    signal_text = (
        f"Entry Confirmed!\n"
        f"Mines Count: {mines_count}\n"
        f"Attempts: {attempts_count}\n"
        f"Valid for: 5 minutes\n\n"
        f"Play {play_url}\n\n"
        f"{grid_text}"
    )
    return signal_text


async def _send_5_min_warning(context: ContextTypes.DEFAULT_TYPE):
    """发送 5 分钟提醒，优先使用缓存的 sticker_file_id，失败尝试本地 .tgs 并回写。"""
    chat_id = context.bot_data['target_chat_id']
    bot_conf = context.bot_data.get('bot_config', {}) or {}
    sticker_id = bot_conf.get('sticker_file_id')
    # 若有缓存的 sticker_file_id 直接发送；否则尝试用本地 .tgs 上传一次并回写数据库
    if sticker_id:
        try:
            await context.bot.send_sticker(chat_id, sticker=sticker_id)
        except Exception:
            pass
    else:
        try:
            from pathlib import Path
            tgs_path = Path(__file__).resolve().parent / 'facai.tgs'
            if tgs_path.exists():
                with open(tgs_path, 'rb') as f:
                    msg = await context.bot.send_sticker(chat_id, sticker=f)
                fid = getattr(getattr(msg, 'sticker', None), 'file_id', None)
                if fid:
                    try:
                        from afubot.bot import database as afu_db
                        afu_db.update_bot_file_ids(bot_conf.get('bot_token'), sticker_file_id=fid)
                    except Exception:
                        pass
                    bot_conf['sticker_file_id'] = fid
                    context.bot_data['bot_config'] = bot_conf
        except Exception:
            pass

    await context.bot.send_message(chat_id=chat_id, text="💎💎💎 Only 5 minutes left 💎💎💎")


async def _send_3_min_warning(context: ContextTypes.DEFAULT_TYPE):
    """发送 3 分钟提醒。"""

    await image_file(context,'gogogo')
    await context.bot.send_message(chat_id=context.bot_data['target_chat_id'], text="💎💎💎 Only 3 minutes left 💎💎💎")


async def _send_1_min_warning(context: ContextTypes.DEFAULT_TYPE):
    """发送 1 分钟提醒。"""

    await tgs_file(context,'boom')
    await context.bot.send_message(chat_id=context.bot_data['target_chat_id'], text="💎💎💎 Only 1 minute left 💎💎💎")


async def _send_success_and_unlock(context: ContextTypes.DEFAULT_TYPE):
    """发送成功提示并解锁下一次发送；每 3 轮追加一次素材轮播。"""
    await context.bot.send_message(chat_id=context.bot_data['target_chat_id'], text="✅ ✅ ✅ Mine-Clearing Successful! ✅ ✅ ✅")
    await tgs_file(context,"dogwin")


    context.bot_data['is_signal_active'] = False
    logger.info(f"[{context.bot_data.get('agent_name')}] 信号已结束，锁已解除。")
    try:
        # 在解锁后，自动安排下一次发送，避免“仅首发一次就停止”的体验
        delay = random.uniform(6, 8)
        context.job_queue.run_once(_send_signal, when=delay)
        logger.info(f"[{context.bot_data.get('agent_name')}] 已计划在 {delay:.1f}s 后再次触发发送。")
    except Exception as e:
        logger.warning(f"[{context.bot_data.get('agent_name')}] 计划再次触发发送失败: {e}")

    # --- 累计轮次：每完成 2 轮后发送一次带单素材（共 12轮覆盖四条） ---
    try:
        rounds = context.bot_data.get('rounds_completed', 0) + 1
        context.bot_data['rounds_completed'] = rounds

        if rounds % 2 == 0:
            materials = getattr(config, 'OVER_MATERIALS', []) or []
            if materials:
                # idx = context.bot_data.get('over_material_index', 0)
                # mat = materials[idx % len(materials)]
                bag = context.bot_data.get('over_material_bag')
                if not isinstance(bag, list) or not bag:
                    bag = list(range(len(materials)))
                    random.shuffle(bag)

                idx = bag[-1]
                mat = materials[idx]
                # image_url = mat.get('image_url')
                # caption = mat.get('caption')
                #
                # image_file_ids = context.bot_data.get('image_file_ids', {})
                # if image_url in image_file_ids:
                #     fid = image_file_ids[image_url]
                #     try:
                #         await context.bot.send_photo(chat_id=context.bot_data['target_chat_id'], photo=fid, caption=caption)
                #     except Exception as e:
                #         logger.warning(f"[{context.bot_data.get('agent_name')}] 发送带单缓存图片失败: {e}")
                # else:
                #     try:
                #         msg = await context.bot.send_photo(chat_id=context.bot_data['target_chat_id'], photo=image_url, caption=caption)
                #         if getattr(msg, 'photo', None):
                #             image_file_ids[image_url] = msg.photo[-1].file_id
                #             context.bot_data['image_file_ids'] = image_file_ids
                #     except Exception as e:
                #         logger.warning(f"[{context.bot_data.get('agent_name')}] 发送带单图片失败: {e}")

                # 三组素材按顺序轮换
                u = (mat.get('image_url') or '').strip()
                caption = mat.get('caption')

                # 简单按后缀判断类型（去掉查询串并转小写）
                base = u.split('?', 1)[0].lower()
                is_tgs = base.endswith('.tgs')
                is_gif = base.endswith('.gif')
                is_video = base.endswith(('.mp4', '.mov', '.m4v', '.webm'))  # 建议优先 mp4

                if is_tgs:
                    # Telegram 动态贴纸（.tgs）用 send_sticker；不支持 caption，如需文案可单独再发
                    sticker_cache = context.bot_data.get('sticker_file_ids', {})
                    cached = sticker_cache.get(u) or ((context.bot_data.get('bot_config') or {}).get('sticker_file_id'))
                    if cached:
                        await context.bot.send_sticker(chat_id=context.bot_data['target_chat_id'], sticker=cached)
                    else:
                        msg = await context.bot.send_sticker(chat_id=context.bot_data['target_chat_id'], sticker=u)
                        try:
                            fid = getattr(getattr(msg, 'sticker', None), 'file_id', None)
                            if fid:
                                sticker_cache[u] = fid
                                context.bot_data['sticker_file_ids'] = sticker_cache
                                try:
                                    if afu_db:
                                        afu_db.update_bot_file_ids((context.bot_data.get('bot_config') or {}).get('bot_token'), sticker_file_id=fid)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                elif is_gif:
                    # GIF 用 send_animation；单独维护动画缓存，避免与图片/视频混用
                    anim_cache = context.bot_data.get('animation_file_ids', {})
                    cached = anim_cache.get(u)
                    if cached:
                        msg = await context.bot.send_animation(chat_id=context.bot_data['target_chat_id'],
                                                               animation=cached, caption=caption)
                    else:
                        msg = await context.bot.send_animation(chat_id=context.bot_data['target_chat_id'], animation=u,
                                                               caption=caption)
                        try:
                            fid = getattr(getattr(msg, 'animation', None), 'file_id', None)
                            if fid:
                                anim_cache[u] = fid
                                context.bot_data['animation_file_ids'] = anim_cache
                        except Exception:
                            pass

                elif is_video:
                    # 视频用 send_video；单独维护视频缓存
                    video_cache = context.bot_data.get('video_file_ids', {})
                    cached = video_cache.get(u)
                    if cached:
                        msg = await context.bot.send_video(chat_id=context.bot_data['target_chat_id'], video=cached,
                                                           caption=caption)
                    else:
                        msg = await context.bot.send_video(chat_id=context.bot_data['target_chat_id'], video=u,
                                                           caption=caption)
                        try:
                            fid = getattr(getattr(msg, 'video', None), 'file_id', None)
                            if fid:
                                video_cache[u] = fid
                                context.bot_data['video_file_ids'] = video_cache
                        except Exception:
                            pass

                else:
                    # 仍按图片发送（复用你现有的图片缓存逻辑）
                    image_file_ids = context.bot_data.get('image_file_ids', {})
                    if u in image_file_ids:
                        fid = image_file_ids[u]
                        try:
                            await context.bot.send_photo(chat_id=context.bot_data['target_chat_id'], photo=fid,
                                                         caption=caption)
                        except Exception as e:
                            logger.warning(f"[{context.bot_data.get('agent_name')}] 发送带单缓存图片失败: {e}")
                    else:
                        try:
                            msg = await context.bot.send_photo(chat_id=context.bot_data['target_chat_id'], photo=u,
                                                               caption=caption)
                            if getattr(msg, 'photo', None):
                                image_file_ids[u] = msg.photo[-1].file_id
                                context.bot_data['image_file_ids'] = image_file_ids
                        except Exception as e:
                            logger.warning(f"[{context.bot_data.get('agent_name')}] 发送带单图片失败: {e}")

                # 成功发送后再消费洗牌袋（保持你原有两行）
                bag.pop()
                context.bot_data['over_material_bag'] = bag
    except Exception as e:
        logger.warning(f"[{context.bot_data.get('agent_name')}] 带单素材发送流程出错: {e}")


async def _send_signal(context: ContextTypes.DEFAULT_TYPE):
    """核心发送逻辑：

    - 支持 `force` 强制发送（用于权限恢复或手动触发）
    - 简化并发：基于 `is_signal_active` 加轻量陈旧锁清理
    - 发送预告、图片（按次数轮换）、主信号文本与倒计时提醒
    """
    # 支持强制发送：当权限刚恢复时即刻首发
    force = False
    try:
        job = getattr(context, 'job', None)
        data = getattr(job, 'data', None) if job else None
        if isinstance(data, dict) and data.get('force'):
            force = True
    except Exception:
        force = False

    logger.info(f"[{context.bot_data.get('agent_name')}] [SEND] enter force={force}, is_active={context.bot_data.get('is_signal_active', False)}, target={context.bot_data.get('target_chat_id')}")

    if not force and context.bot_data.get('is_signal_active', False):
        # 如果超过5分钟仍为占用，认定为陈旧锁，清除后继续；否则跳过
        last = context.bot_data.get('last_signal_time', 0)
        age = int(time.time() - last)
        if age > 300:
            logger.warning(f"[{context.bot_data.get('agent_name')}] [SEND] detected stale lock {age}s, force releasing")
            context.bot_data['is_signal_active'] = False
        else:
            logger.info(f"[{context.bot_data.get('agent_name')}] [SEND] skip because is_signal_active=True (last={age}s)")
            return

    # 抢占锁：在真正发送前先设置为占用，避免并发重复触发
    context.bot_data['is_signal_active'] = True
    context.bot_data['last_signal_time'] = time.time()

    try:
        call_count = context.bot_data.get('signal_call_count', 0) + 1
        context.bot_data['signal_call_count'] = call_count
        target_chat = context.bot_data['target_chat_id']
        bot_conf = context.bot_data.get('bot_config')
        agent_name = context.bot_data.get('agent_name')
        logger.info(f"[{agent_name}] 信号任务触发第 {call_count} 次 -> {target_chat}")

        # 去掉 sendnow 门槛，任何时候都可由调度或手动触发

        # 每次发送前置提示（英式印地语/Hinglish），再等待 1s
        try:
            pretext = "📶 Signal detect ho gaya 🚥"
            await context.bot.send_message(chat_id=target_chat, text=pretext)
            await asyncio.sleep(2)
            await tgs_file(context, 'shejian')
        except Exception:
            pass

        if call_count % 3 == 1:
            try:
                # 尝试使用缓存的图片file_id
                image_file_ids = context.bot_data.get('image_file_ids', {})
                image_url = random.choice(config.IMAGE_LIBRARY['firstdd'])
                caption_text = "\n✨ Follow my lead and enter the new game adventure!\n\n🎮 Ready? Let's go."

                # 如果有缓存的file_id，直接使用
                if image_url in image_file_ids:
                    photo = image_file_ids[image_url]
                    msg = await context.bot.send_photo(chat_id=target_chat, photo=photo, caption=caption_text)
                    logger.info(f"[{agent_name}] [SEND] sent cached image -> msg_id={getattr(msg, 'message_id', None)}")
                else:
                    # 否则上传并缓存file_id
                    message = await context.bot.send_photo(chat_id=target_chat, photo=image_url, caption=caption_text)
                    if message.photo:
                        # 缓存file_id以便下次使用
                        image_file_ids[image_url] = message.photo[-1].file_id
                        context.bot_data['image_file_ids'] = image_file_ids
                        logger.info(f"[{agent_name}] [SEND] uploaded image and cached file_id")

                await asyncio.sleep(random.uniform(1, 2))  # 减少等待时间
            except Exception as e:
                logger.warning(f"[{agent_name}] 发送图片失败: {e}")

        # 不再发送“检查信号”提示，直接进入信号内容
        await asyncio.sleep(random.uniform(1, 2))

        signal_message = generate_signal_message(bot_conf)
        try:
            msg = await context.bot.send_message(chat_id=target_chat, text=signal_message)
            logger.info(f"[{agent_name}] [SEND] sent signal text -> msg_id={getattr(msg, 'message_id', None)}")
        except Exception as e:
            logger.error(f"[{agent_name}] 发送信号文本失败: {e}")
            context.bot_data['is_signal_active'] = False
            return
        logger.info(f"[{agent_name}] 成功发送一条信号 -> {target_chat}")

        job_queue = context.job_queue
        # 恢复完整倒计时提醒
        job_queue.run_once(_send_5_min_warning, 3)
        job_queue.run_once(_send_3_min_warning, 12)  #生产为120
        job_queue.run_once(_send_1_min_warning, 24) #生产为240
        job_queue.run_once(_send_success_and_unlock, 30) #生产为300
    except Exception as e:
        logger.error(f"[{context.bot_data.get('agent_name')}] 发送信号失败: {e}")
        context.bot_data['is_signal_active'] = False


async def _schedule_checker(context: ContextTypes.DEFAULT_TYPE):
    """概率调度器：每分钟检查一次，并按时间间隔调整触发概率。"""
    # 如果机器人被暂停，则跳过发送
    if context.bot_data.get('paused', False):
        return

    # 检查上次发送时间，避免频繁发送
    last_signal_time = context.bot_data.get('last_signal_time', 0)
    current_time = time.time()

    # 如果距离上次发送不足10分钟，则降低发送概率
    time_diff = current_time - last_signal_time
    if time_diff < 600:  # 10分钟
        probability = PROBABILITY_PER_MINUTE * (time_diff / 600)
    else:
        probability = PROBABILITY_PER_MINUTE

    if random.random() < probability:
        # 若被遗留锁占用（例如异常未解锁），这里强制清除后再触发一次
        if context.bot_data.get('is_signal_active', False) and (current_time - last_signal_time) > 600:
            logger.warning(f"[{context.bot_data.get('agent_name')}] 检测到遗留锁超过10分钟，强制清理")
            context.bot_data['is_signal_active'] = False
        asyncio.create_task(_send_signal(context))


# HTTP 请求处理器在应用创建时按需实例化，避免跨线程/事件循环复用

async def _create_and_start_app(bot_token: str, target_chat_id: str, bot_config: dict | None = None) -> Application:
    """创建并启动一个用于频道发送的 `Application`。

    - 在 `bot_data` 中设置目标频道、配置与运行状态
    - 安排概率调度器与首次发送
    """
    # 在当前事件循环中创建 HTTPXRequest，避免“bound to a different event loop”错误
    request = HTTPXRequest(connection_pool_size=100)
    app = ApplicationBuilder().token(bot_token).request(request).build()
    # 仅日志的全局错误处理器
    async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled exception in axibot app", exc_info=context.error)
    app.add_error_handler(_on_error)
    app.bot_data['target_chat_id'] = target_chat_id
    app.bot_data['bot_config'] = bot_config or {}
    app.bot_data['agent_name'] = (bot_config or {}).get('agent_name', 'Agent')
    app.bot_data['last_signal_time'] = 0  # 记录上次发送信号的时间
    app.bot_data['image_file_ids'] = {}  # 缓存已上传的图片文件ID
    app.bot_data['is_signal_active'] = False  # 启动时确保无锁
    # 轮播素材相关：记录已完成的轮次数与下次素材索引
    app.bot_data['rounds_completed'] = 0
    app.bot_data['over_material_index'] = 0
    logger.info(f"[{app.bot_data['agent_name']}] [START] app created -> target={target_chat_id}")

    # 安排重复性任务
    job_queue = app.job_queue
    # 1) 保留原每分钟检查（概率触发）
    job_queue.run_repeating(_schedule_checker, interval=60, first=10)
    logger.info(f"[{app.bot_data['agent_name']}] [SCHED] schedule_checker every 60s, first=10s")
    # 仅使用概率调度，取消固定配额调度（按你的要求）

    await app.initialize()
    # 仅发送，不强制需要轮询；但为了保持一致性，仍然启动轮询（可接收 / 健康检查等）
    await app.updater.start_polling(drop_pending_updates=True)  # 丢弃积压的更新以减少启动时的负载
    await app.start()

    # 将首次触发放到应用完全启动之后，避免未启动scheduler时丢失
    job_queue.run_once(_send_signal, when=2)
    logger.info(f"[{app.bot_data['agent_name']}] [SCHED] priming first _send_signal in 2s")

    logger.info(f"启动发送应用 -> [{app.bot_data['agent_name']}] -> {target_chat_id}")
    return app


class AxiBotManager:
    def __init__(self):
        self.running_bots = {}  # token -> Application
        self.last_check_time = 0
        self.check_interval = 15  # 每15秒检查一次新机器人，保证更快拾取
        self.bot_status = {}  # token -> {"last_error": time, "error_count": int}
        self._stop_event = threading.Event()
        self._monitor_thread = None
        self.shared_resources = {
            "image_cache": {},  # 缓存图片以减少重复上传
            "active_hours": {}  # 机器人活跃时间 {token: [hour_ranges]}
        }

    async def start_bot(self, bot_config):
        """启动一个频道机器人（若已运行则复用并进行权限检查）。"""
        token = bot_config.get('bot_token')
        channel = _normalize_channel_link(bot_config.get('channel_link'))

        if not token or not channel:
            logger.warning(f"机器人配置缺少token或channel: {bot_config}")
            return None

        if token in self.running_bots:
            logger.info(f"机器人 {bot_config.get('agent_name')} 已在运行中")
            # 如果机器人已在运行，检查权限是否已更新
            if token in self.bot_status and self.bot_status[token].get('error_count', 0) > 0:
                await self.check_bot_permissions(self.running_bots[token], channel, bot_config)
            return self.running_bots[token]

        try:
            app = await _create_and_start_app(token, channel, bot_config)
            self.running_bots[token] = app
            # 初始化状态
            self.bot_status[token] = {
                "last_error": 0,
                "error_count": 0,
                "last_check": time.time()
            }
            # 检查权限
            await self.check_bot_permissions(app, channel, bot_config)
            logger.info(f"成功启动机器人 {bot_config.get('agent_name')} -> {channel}")
            # 启动后不再发送提示文本，避免打扰用户
            return app
        except Exception as e:
            logger.error(f"启动机器人失败 {bot_config.get('agent_name')}: {e}")
            return None

    async def stop_bot(self, token):
        """停止一个频道机器人并清理计划任务。"""
        if token not in self.running_bots:
            return

        app = self.running_bots[token]
        try:
            # 停止前先移除该应用的所有计划任务，避免停止后仍触发
            try:
                for job in list(app.job_queue.jobs()):
                    try:
                        job.schedule_removal()
                    except Exception:
                        pass
                for job in app.job_queue.get_jobs_by_name("_schedule_checker"):
                    try:
                        job.schedule_removal()
                    except Exception:
                        pass
            except Exception:
                pass
            if app.updater and app.updater._running:
                await app.updater.stop()
            await app.stop()
            await app.shutdown()
            del self.running_bots[token]
            logger.info(f"停止机器人 [{app.bot_data.get('agent_name')}]")
        except Exception as e:
            logger.error(f"停止机器人出错: {e}")

    async def trigger_send_now(self, token):
        """强制立即触发一次发送（如果机器人已在运行）。"""
        app = self.running_bots.get(token)
        if not app:
            logger.warning(f"trigger_send_now: 机器人未运行: {token}")
            return False
        try:
            # 清理忙碌标记
            app.bot_data['is_signal_active'] = False
            app.bot_data['last_signal_time'] = 0

            # 直接调用发送逻辑，避免作业调度器偶发不触发
            from types import SimpleNamespace
            ctx = SimpleNamespace(
                bot=app.bot,
                bot_data=app.bot_data,
                application=app,
                job_queue=app.job_queue,
                job=SimpleNamespace(data={"force": True}),
            )
            await _send_signal(ctx)
            logger.info(f"trigger_send_now: 已直接执行一次发送 -> {app.bot_data.get('agent_name')}")
            return True
        except Exception as e:
            logger.error(f"trigger_send_now 失败: {e}")
            return False

    async def check_bot_permissions(self, app, channel_id, bot_config=None):
        """检查机器人在频道中的权限（不发测试消息）。
        - 管理员且有发帖/发言权限视为通过；否则计数并提示
        - 当权限从异常恢复时，自动安排一次强制发送
        """
        token = app.bot.token
        agent_name = app.bot_data.get('agent_name')

        try:
            # 通过 get_me 拿到自身 id
            me = await app.bot.get_me()
            member = await app.bot.get_chat_member(chat_id=channel_id, user_id=me.id)
            status = getattr(member, 'status', None)

            # Telegram 频道：需要管理员且可发帖
            can_post = True
            # 不同类型的 ChatMember 上权限字段可能不同，做容错读取
            for field in (
                'can_post_messages',       # 频道发帖
                'can_send_messages',       # 超级群发言
            ):
                if hasattr(member, field):
                    can_post = bool(getattr(member, field))
                    break

            if status in ("administrator", "creator") and can_post:
                # 权限通过，重置错误计数
                prev_error_count = 0
                if token in self.bot_status:
                    prev_error_count = self.bot_status[token].get('error_count', 0)
                    self.bot_status[token]['error_count'] = 0
                    self.bot_status[token]['last_check'] = time.time()
                logger.info(f"机器人 {agent_name} 在频道 {channel_id} 权限正常（{status}）")

                # 如果之前权限检查失败过，现在刚恢复正常，立即触发一次发送
                if prev_error_count > 0:
                    try:
                        logger.info(f"[{agent_name}] 权限恢复，立即触发一次发送任务以验证 (force)")
                        # 清除可能残留的“信号进行中”标记，确保不会被跳过
                        app.bot_data['is_signal_active'] = False
                        app.bot_data['last_signal_time'] = 0
                        app.job_queue.run_once(_send_signal, when=2, data={"force": True})
                    except Exception as e:
                        logger.warning(f"[{agent_name}] 触发恢复发送失败: {e}")
                return True
            else:
                prev_error = 0
                if token in self.bot_status:
                    prev_error = self.bot_status[token].get('error_count', 0)
                logger.error(f"机器人 {agent_name} 在频道 {channel_id} 权限不足（status={status}, can_post={can_post}），连续失败次数：{prev_error + 1}")
                # 记录错误
                if token not in self.bot_status:
                    self.bot_status[token] = {"error_count": 0, "last_error": 0, "last_check": time.time()}
                self.bot_status[token]['error_count'] += 1
                self.bot_status[token]['last_error'] = time.time()
                return False

        except (Forbidden, BadRequest) as e:
            if token not in self.bot_status:
                self.bot_status[token] = {"error_count": 0, "last_error": 0, "last_check": time.time()}
            self.bot_status[token]['error_count'] += 1
            self.bot_status[token]['last_error'] = time.time()

            if isinstance(e, Forbidden):
                logger.error(f"机器人 {agent_name} 没有在频道 {channel_id} 的访问权限")
            elif "chat not found" in str(e).lower():
                logger.error(f"频道 {channel_id} 不存在或机器人 {agent_name} 不在频道中")
            else:
                logger.error(f"检查机器人 {agent_name} 权限时出错: {e}")
            return False

        except Exception as e:
            logger.error(f"检查机器人 {agent_name} 权限时出现未知错误: {e}")
            return False

    def _is_active_hour(self, token, current_hour):
        """检查当前时间是否在机器人的活跃时间范围内。"""
        active_hours = self.shared_resources["active_hours"].get(token)
        if not active_hours:  # 如果没有设置活跃时间，则默认全天活跃
            return True
        return current_hour in active_hours

    async def set_bot_active_hours(self, token, hours_list):
        """设置活跃时间，如 [9,10,...,22]，并热更新到运行应用。"""
        self.shared_resources["active_hours"][token] = hours_list
        if token in self.running_bots:
            app = self.running_bots[token]
            app.bot_data['active_hours'] = hours_list
            logger.info(f"已设置机器人 {app.bot_data.get('agent_name')} 的活跃时间为 {hours_list}")

    async def pause_bot(self, token):
        """暂停机器人（仅置标志，不停止应用）。"""
        if token in self.running_bots:
            app = self.running_bots[token]
            app.bot_data['paused'] = True
            logger.info(f"已暂停机器人 {app.bot_data.get('agent_name')}")

    async def resume_bot(self, token):
        """恢复之前暂停的机器人。"""
        if token in self.running_bots:
            app = self.running_bots[token]
            app.bot_data['paused'] = False
            logger.info(f"已恢复机器人 {app.bot_data.get('agent_name')}")

    async def check_new_bots(self):
        """从 afubot 数据库拉取频道机器人并做动态管理（启动/暂停/恢复/权限检查）。"""
        if afu_db is None:
            return

        try:
            current_time = time.time()
            current_hour = datetime.datetime.now().hour

            # 获取所有活跃的频道机器人
            active_bots = afu_db.get_active_bots(role='channel')
            active_tokens = set(bot['bot_token'] for bot in active_bots)

            # 停止已被删除或停用的机器人
            for token in list(self.running_bots.keys()):
                if token not in active_tokens:
                    logger.info(f"机器人 {token} 已从数据库中删除或停用，正在停止...")
                    await self.stop_bot(token)

            # 按需管理机器人
            for bot in active_bots:
                token = bot['bot_token']

                # 检查是否在活跃时间内
                is_active_hour = self._is_active_hour(token, current_hour)

                if token not in self.running_bots:
                    # 只在活跃时间内启动新机器人
                    if is_active_hour:
                        logger.info(f"发现新机器人 {bot['agent_name']}，正在启动...")
                        app = await self.start_bot(bot)
                        if app:
                            # 设置活跃时间
                            active_hours = self.shared_resources["active_hours"].get(token, [])
                            app.bot_data['active_hours'] = active_hours
                else:
                    app = self.running_bots[token]

                    # 根据活跃时间暂停或恢复机器人
                    if is_active_hour and app.bot_data.get('paused', False):
                        await self.resume_bot(token)
                    elif not is_active_hour and not app.bot_data.get('paused', False):
                        await self.pause_bot(token)

                    # 检查已运行机器人的权限状态
                    channel = _normalize_channel_link(bot.get('channel_link'))

                    # 如果上次检查失败或超过一定时间则重新检查
                    status = self.bot_status.get(token, {})
                    last_check = status.get('last_check', 0)
                    error_count = status.get('error_count', 0)

                    # 如果有错误或者超过300秒没有检查过权限，则重新检查
                    if error_count > 0 or (current_time - last_check) > 300:
                        logger.info(f"重新检查机器人 {bot['agent_name']} 的权限状态")
                        await self.check_bot_permissions(app, channel, bot)

            self.last_check_time = current_time
        except Exception as e:
            logger.error(f"检查新机器人时出错: {e}")

    async def start_all_bots(self):
        """启动所有活跃的频道机器人（从 afubot 数据库获取）。"""
        if afu_db is None:
            raise RuntimeError("无法导入 afubot.bot.database，无法获取频道与机器人配置。")

        try:
            # 仅启动频道带单机器人
            active_bots = afu_db.get_active_bots(role='channel')
            for bot in active_bots:
                await self.start_bot(bot)

            if not self.running_bots:
                logger.warning("数据库中没有带有效 channel_link 的活跃机器人，Axibot 将等待新机器人添加。")
            else:
                logger.info(f"Axibot 已启动 {len(self.running_bots)} 个发送应用。")
        except Exception as e:
            logger.error(f"从 afu 数据库加载机器人失败: {e}")
            raise

    def start_monitor(self):
        """启动后台监控线程，定期检查新机器人与权限。"""
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_task)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()
        logger.info("后台监控线程已启动，将定期检查新机器人")

    def stop_monitor(self):
        """停止后台监控线程。"""
        if self._monitor_thread:
            self._stop_event.set()
            self._monitor_thread.join(timeout=2)
            logger.info("后台监控线程已停止")

    def _monitor_task(self):
        """后台监控任务：在独立事件循环中定期调度 `check_new_bots`。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while not self._stop_event.is_set():
            current_time = time.time()
            if current_time - self.last_check_time >= self.check_interval:
                loop.run_until_complete(self.check_new_bots())
            time.sleep(1)

    async def shutdown_all(self):
        """关闭所有运行中的机器人并停止监控。"""
        self.stop_monitor()
        for token in list(self.running_bots.keys()):
            await self.stop_bot(token)


async def startup():
    """Axibot 启动：从 afubot 数据库读取频道机器人，启动并进入监控。"""
    logger.info("Axibot 启动中（仅数据库模式）...")

    if afu_db is None:
        raise RuntimeError("无法导入 afubot.bot.database，无法获取频道与机器人配置。")

    manager = AxiBotManager()
    await manager.start_all_bots()
    manager.start_monitor()

    logger.info("Axibot 已启动并开始监控新机器人")
    return manager


async def shutdown(manager: AxiBotManager):
    """Axibot 优雅关闭：停止所有应用并结束。"""
    logger.info("正在关闭 Axibot...")
    await manager.shutdown_all()
    logger.info("所有机器人应用已关闭。")


if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.get_event_loop()
    manager = None

    try:
        manager = loop.run_until_complete(startup())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("检测到手动中断 (Ctrl+C)，开始优雅关闭...")
    finally:
        if manager is not None:
            loop.run_until_complete(shutdown(manager))
        logger.info("程序已完全关闭。")


