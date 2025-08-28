import settings as _S

# --- 图片/媒体库 (URL) ---
IMAGE_LIBRARY = {
    'registration': _S.IMAGE_LIBRARY.get('registration', []),
    'deposit': _S.IMAGE_LIBRARY.get('deposit', []),
    'firstdd': _S.IMAGE_LIBRARY.get('firstdd', [])

}

# 仅保留媒体库配置；Axibot 现在强制依赖 afubot 数据库中的 channel_link、bot_token 等信息。




# --- 轮次结束追加素材（三组循环） ---
# 每一轮结束后会按顺序发送一条图片+文案，并在第三组后回到第一组。
OVER_MATERIALS = [
    {
        "image_url": "https://storage.googleapis.com/axibot/dan/over1.jpg",
        "caption": (
            "🎮 Minefield Game Tips & Tricks\n"
            "✨ Step 1: Rules samajh lo\n"
            "Game ka main goal hai safe boxes open karna ✅ aur mines 💣 avoid karna.\n"
            "Yaad rakho, har ek choice independent hoti hai, pehle wale se koi connection nahi.\n"
            "✨ Step 2: Small boards se start karo\n"
            "Agar tum beginner ho toh chhote board pe khelo (kam boxes).\n"
            "Isse game fast pace hoga, easy to understand hoga aur tumhe confidence milega.\n"
            "✨ Step 3: Prediction & logic use karo\n"
            "Channel version mein tips ya probability hints milte hain 🔍\n"
            "Un hints ka use karo aur guess karo kaunsa area zyada safe hai.\n"
            "Iss se tumhari chances of winning badh jaayengi.\n"
            "✨ Step 4: Mindset strong rakho\n"
            "Game mein randomness part of the fun hai.\n"
            "Jaldi mat karo, ise ek observation aur logic practice game samjho. 🎉\n"
            "Aise khelne se game aur mazedaar ban jaata hai 😎"
        ),
    },
    {
        "image_url": "https://storage.googleapis.com/axibot/dan/over2.jpg",
        "caption": (
            "⏰ The clock is ticking — money loves speed.\n"
            "While you’re doubting, someone else is starting the engine of their dream. — want the same?\n"
            "Take action! 🕶️🤑"
        ),
    },
    {
        "image_url": "https://storage.googleapis.com/axibot/dan/over3.jpg",
        "caption": (
            "💸 Best proof yaar, jab paisa actually tere haath mein hota hai 🙌\n"
            "❌ No fake promises, only asli results ✅\n"
            "🔥 Chahiye same result? Try karna shuru karo abhi 👉🚀"
        ),
    },
    {
        "image_url": "https://storage.googleapis.com/axibot/dan/over4.jpg",
        "caption": (
            "🎮 Mines fund allocation strategy — bot ke signals follow karo.\n"
            "💱 Ek game mein kitna lagana? Suggested single bet = 5–20% of fund.\n"
            "Example: 1000 rupees ho toh per game 50–200 rupees. Safe & continuous play.\n"
            "Consecutive jeet pe thoda increase kar sakte ho — 20% → 30% ✅\n"
            "🎯 Daily profit target: +30% to +50%. Example: 10,000 fund se aaj 3,000–5,000 profit ho gaya toh stop 🛑, kal continue.\n"
            "📈 Fund accumulation thinking: aaj 3,000 win → kal principal 13,000, phir uske hisaab se next bet. 🚀"
        ),
    },
]


