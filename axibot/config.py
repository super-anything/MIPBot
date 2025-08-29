"""axibot 资源配置桥接

该模块仅承载图片/媒体库常量，实际的频道/Token 等运行配置
统一由 afubot 的数据库提供（参见 `afubot.bot.database`）。
"""

import settings as _S

# --- 图片/媒体库 (URL) ---
IMAGE_LIBRARY = {
    'registration': _S.IMAGE_LIBRARY.get('registration', []),
    'deposit': _S.IMAGE_LIBRARY.get('deposit', []),
    'firstdd': _S.IMAGE_LIBRARY.get('firstdd', [])

}

# 仅保留媒体库配置；Axibot 依赖 afubot 数据库中的 channel_link、bot_token 等信息。




# --- 轮次结束追加素材（9张） ---
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
    {
        "image_url": "https://storage.googleapis.com/axibot/dan/over5.jpg",
        "caption": (
            "✨ Better than any shabd are numbers aur screenshots 📸\n"
           " 💸 Sirf kuch minute mein hi kama liya unbelievable paisa 💰\n"
            "— Yahan log sapne nahi dekhte 😴, directly cash out karte hain 🏦\n"
            "🔥 Same result chahiye? Abhi game start karo 🎮👉"
        )
    },
    {
        "image_url": "https://storage.googleapis.com/axibot/dan/over6.jpg",
        "caption": (
            "🌅 Every morning ek naya chance hai tumhe ek fresh insaan ban’ne ka.\n"
            "Jab dusre log so rahe hote hain 😴 ya complain karte hain 😒 — tum action le sakte ho aur jo tumhara hai wo le sakte ho 💪.\n"
            "✨ Start your day the right way.\n"
            "🔥 Same result chahiye? Abhi click karke game start karo 🎮👉"
        )
    },
    {
        "image_url": "https://storage.googleapis.com/axibot/dan/over7.jpg",
        "caption": (
            "Thode hi log jaante hain 🤫: predictor har second mein hundreds of data points analyze karta hai 📊, taaki tumhe peak dikhaye before it flies 🚀.\n"
            "Ye kismat nahi hai 🍀 — ye AI hai jo tumhare liye kaam kar rahi hai 🤖.\n"
            "— Dusre log jo nahi dekh paate, woh chance dekhna hai? Abhi saamne wali opportunity ko pakdo 💥."
        )
    },
    {
        "image_url": "https://storage.googleapis.com/axibot/dan/over8.jpg",
        "caption": (
            "Sab log kehte hain ki ye impossible hai 😏.\n"
            "Lekin jab kuch log sirf baatein karte hain 🗣 — dusre log sirf kuch minute mein cash out kar lete hain 💸.\n"
            "— Tumhe khud decide karna hai ki kis side khade ho 💪.\n"
            "Ready ho? Paisa kamaana hai ya nahi, choice tumhare haath mein hai 🔥."
        )
    },
    {
        "image_url": "https://storage.googleapis.com/axibot/dan/over9.jpg",
        "caption": (
            "🔥🔥 Dekho yaar, mere student ne mera personal mentoring leke kya zabardast result nikala hai 💯!\n"
            "Bas tumhe new cheezon se darrna band karna hai 😎, thoda risk lena start karo 🚀.\n"
            "Tum sab bhi kar sakte ho, aur mere saath ho toh bilkul safe ho 👍."
        )
    }
]


