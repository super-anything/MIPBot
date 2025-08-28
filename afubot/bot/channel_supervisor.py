import asyncio
import logging
from typing import Dict

from telegram.ext import Application
from telegram.request import HTTPXRequest


logger = logging.getLogger(__name__)


class ChannelSupervisor:
    """极简频道发送管理器：
    - 动态 start/stop 单个机器人
    - send_now 发送一条测试/首发
    - 不做复杂调度，稳定优先
    """

    def __init__(self):
        self.running: Dict[str, Application] = {}  # token -> app

    async def start(self, bot_config: dict) -> Application | None:
        """使用 axibot 的创建函数启动，从而带上 target_chat_id 和调度器。"""
        token = bot_config.get('bot_token')
        if not token:
            return None
        if token in self.running:
            return self.running[token]
        try:
            # 复用 axibot 的创建逻辑，确保设置 target_chat_id、job_queue 等
            from axibot.main import _create_and_start_app, _normalize_channel_link

            channel = _normalize_channel_link(bot_config.get('channel_link'))
            app = await _create_and_start_app(token, channel, bot_config)
            self.running[token] = app
            logger.info(f"ChannelSupervisor: started {bot_config.get('agent_name')} with scheduler.")
            # 新建后立即首发一次，确保“新增即有输出”
            try:
                from axibot.main import _send_signal
                from types import SimpleNamespace
                ctx = SimpleNamespace(
                    bot=app.bot,
                    bot_data=app.bot_data,
                    application=app,
                    job_queue=app.job_queue,
                    job=SimpleNamespace(data={"force": True}),
                )
                await _send_signal(ctx)
                logger.info(f"ChannelSupervisor: first send triggered -> {bot_config.get('agent_name')}")
            except Exception as e:
                logger.warning(f"ChannelSupervisor: 首发失败: {e}")
            return app
        except Exception as e:
            logger.error(f"ChannelSupervisor: start failed: {e}")
            return None

    async def stop(self, token: str):
        app = self.running.get(token)
        if not app:
            return
        try:
            # 先清理该应用上的所有计划任务，避免停止过程中仍有 Job 触发
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
        finally:
            self.running.pop(token, None)
            logger.info("ChannelSupervisor: stopped %s", token)

    async def send_now(self, token: str, text: str | None = None) -> bool:
        app = self.running.get(token)
        if not app:
            return False
        bot_conf = app.bot_data.get('bot_config', {})
        target = bot_conf.get('channel_link')
        if not target:
            return False
        try:
            # 复用 axibot 的发送逻辑
            from axibot.main import _send_signal
            from types import SimpleNamespace
            ctx = SimpleNamespace(
                bot=app.bot,
                bot_data=app.bot_data,
                application=app,
                job_queue=app.job_queue,
                job=SimpleNamespace(data={"force": True}),
            )
            await _send_signal(ctx)
            return True
        except Exception as e:
            logger.error("ChannelSupervisor: send_now failed: %s", e)
            return False

    async def update_config(self, token: str, **fields) -> bool:
        """热更新运行中机器人的配置（例如 play_url）。"""
        app = self.running.get(token)
        if not app:
            return False
        try:
            bot_conf = app.bot_data.get('bot_config') or {}
            bot_conf.update({k: v for k, v in fields.items() if v is not None})
            app.bot_data['bot_config'] = bot_conf
            return True
        except Exception:
            return False


