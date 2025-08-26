import settings as _S

# --- 图片/媒体库 (URL) ---
IMAGE_LIBRARY = {
    'registration': _S.IMAGE_LIBRARY.get('registration', []),
    'deposit': _S.IMAGE_LIBRARY.get('deposit', []),
    'firstdd': _S.IMAGE_LIBRARY.get('firstdd', [])

}

# 仅保留媒体库配置；Axibot 现在强制依赖 afubot 数据库中的 channel_link、bot_token 等信息。




