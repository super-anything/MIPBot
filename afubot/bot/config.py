"""afubot 运行期配置桥接

从项目根 `settings.py` 引入所需配置项，统一暴露给 afubot 代码使用。
- 数据库连接/后端设置
- 管理员机器人 Token 与白名单
- 资源库（首图/注册/存款教学等）

注意：若关键配置缺失，将在 import 阶段抛出异常，尽早暴露配置问题。
"""

import settings as _S

# 统一从根 settings 读取配置
DB_FILE = _S.DB_FILE
DB_BACKEND = _S.DB_BACKEND
MYSQL_HOST = _S.MYSQL_HOST
MYSQL_PORT = _S.MYSQL_PORT
MYSQL_USER = _S.MYSQL_USER
MYSQL_PASSWORD = _S.MYSQL_PASSWORD
MYSQL_DATABASE = _S.MYSQL_DATABASE

ADMIN_BOT_TOKEN = _S.ADMIN_BOT_TOKEN
ADMIN_USER_IDS = _S.ADMIN_USER_IDS

IMAGE_LIBRARY = {
    'find_id': _S.IMAGE_LIBRARY.get('find_id', []),
    'deposit_guide': _S.IMAGE_LIBRARY.get('deposit_guide', []),
    'firstpng': _S.IMAGE_LIBRARY.get('firstpng', [])
}

if not ADMIN_BOT_TOKEN:
    raise ValueError("请在 .env 或 settings.py 中设置 ADMIN_BOT_TOKEN")

if not ADMIN_USER_IDS:
    raise ValueError("请在 settings.py 中设置 ADMIN_USER_IDS 列表")
