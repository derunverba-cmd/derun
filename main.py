import sqlite3
import telebot
from telebot import types

TOKEN = "ВСТАВ_СВІЙ_ТОКЕН"

bot = telebot.TeleBot(TOKEN)

# ---------- База даних ----------
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    money REAL DEFAULT 0,
    game_currency REAL DEFAULT 0
)
""")
db.commit()


def get_user(user_id):
    cur.execute("SELECT money, game_currency FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        db.commit()
        return 0, 0
    return row


# ---------- Меню ----------
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👤 Профіль", "💰 Баланс")
    return kb


@bot.message_handler(commands=["start"])
def start(message):
    get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "Вітаю! Обери розділ меню 👇",
        reply_markup=main_menu(),
    )


@bot.message_handler(func=lambda m: m.text == "👤 Профіль")
def profile(message):
    get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"👤 Профіль\n\nАйді: {message.from_user.id}",
    )


@bot.message_handler(func=lambda m: m.text == "💰 Баланс")
def balance(message):
    money, game = get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "💰 Баланс\n\n"
        f"Кошти: {money}\n"
        f"Ігрова валюта: {game}\n"
        "Донат валюта: скоро",
    )


print("Бот запущено")
bot.infinity_polling()
