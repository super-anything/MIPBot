import asyncio
import logging
from typing import Dict

from telegram.ext import Application, ApplicationBuilder, ContextTypes
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
        token = bot_config.get('bot_token')
        if not token:
            return None
        if token in self.running:
            return self.running[token]
        try:
            request = HTTPXRequest(connection_pool_size=50)
            app = ApplicationBuilder().token(token).request(request).build()
            app.bot_data['bot_config'] = bot_config
            await app.initialize()
            await app.updater.start_polling(drop_pending_updates=True)
            await app.start()
            self.running[token] = app
            logger.info(f"ChannelSupervisor: started {bot_config.get('agent_name')}.")
            return app
        except Exception as e:
            logger.error(f"ChannelSupervisor: start failed: {e}")
            return None

    async def stop(self, token: str):
        app = self.running.get(token)
        if not app:
            return
        try:
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
            await app.bot.send_message(chat_id=target, text=text or "Bot activated. Preparing first signal...")
            return True
        except Exception as e:
            logger.error("ChannelSupervisor: send_now failed: %s", e)
            return False


