from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# “是/否”选择键盘
yes_no_keyboard = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("是 (Yes)", callback_data="yes"),
        InlineKeyboardButton("否 (No)", callback_data="no"),
    ]
])
