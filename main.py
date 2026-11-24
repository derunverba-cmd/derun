import os
import sqlite3
import telebot
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    from config import TOKEN  # локальний файл для Pydroid3

ADMIN_ID = 7660211311
CARD = "4874 0700 6372 5947"
MIN_TOPUP = 10

bot = telebot.TeleBot(TOKEN)

# ---------- База даних ----------
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    money REAL DEFAULT 0,
    game_currency REAL DEFAULT 0,
    total_bought INTEGER DEFAULT 0,
    total_sold INTEGER DEFAULT 0
)
""")

# якщо стара база без нових колонок - додаємо їх
cur.execute("PRAGMA table_info(users)")
columns = [row[1] for row in cur.fetchall()]
if "total_bought" not in columns:
    cur.execute("ALTER TABLE users ADD COLUMN total_bought INTEGER DEFAULT 0")
if "total_sold" not in columns:
    cur.execute("ALTER TABLE users ADD COLUMN total_sold INTEGER DEFAULT 0")

cur.execute("""
CREATE TABLE IF NOT EXISTS topups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    status TEXT   -- waiting_receipt / pending / approved / rejected
)
""")
db.commit()


def get_user(user_id):
    cur.execute(
        "SELECT money, game_currency, total_bought, total_sold "
        "FROM users WHERE user_id = ?",
        (user_id,),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        db.commit()
        return 0, 0, 0, 0
    return row


def fmt(n):
    return f"{n:g}"


# ---------- Головне меню ----------
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✈️Профіль", "💸Balance")
    return kb


@bot.message_handler(commands=["start"])
def start(message):
    get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "Вітаю! Обери розділ меню 👇",
        reply_markup=main_menu(),
    )


# ---------- Профіль ----------
@bot.message_handler(func=lambda m: m.text == "✈️Профіль")
def profile(message):
    get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"✈️Профіль\n\n🆔: {message.from_user.id}",
    )


# ---------- Баланс ----------
def balance_text(user_id):
    money, game, bought, sold = get_user(user_id)
    return (
        "💸Balance\n\n"
        f"⭐️Кошти: {fmt(money)}₴\n"
        f"Валюта ігрова: {fmt(game)}\n"
        "Донат Валюта: СКОРО\n\n"
        f"Всього куплено: {bought}\n\n"
        f"Всього продано: {sold}"
    )


def wallet_button():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💸 Гаманець", callback_data="wallet"))
    return kb


def wallet_actions():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("Поповнити", callback_data="topup"),
        types.InlineKeyboardButton("Вивести", callback_data="withdraw"),
    )
    return kb


@bot.message_handler(func=lambda m: m.text == "💸Balance")
def balance(message):
    bot.send_message(
        message.chat.id,
        balance_text(message.from_user.id),
        reply_markup=wallet_button(),
    )


# натиснули "Гаманець" -> під повідомленням з'являються 2 кнопки
@bot.callback_query_handler(func=lambda c: c.data == "wallet")
def wallet(call):
    bot.edit_message_reply_markup(
        call.message.chat.id,
        call.message.message_id,
        reply_markup=wallet_actions(),
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data == "withdraw")
def withdraw(call):
    bot.answer_callback_query(call.id, "Поки що не доступно", show_alert=True)


# ---------- Поповнення ----------
@bot.callback_query_handler(func=lambda c: c.data == "topup")
def topup(call):
    # видаляємо старе повідомлення
    bot.delete_message(call.message.chat.id, call.message.message_id)

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("⭐️ Зірками", callback_data="topup_stars"),
        types.InlineKeyboardButton("💳 На карту", callback_data="topup_card"),
    )
    bot.send_message(call.message.chat.id, "Поповнення\n\nОберіть спосіб:", reply_markup=kb)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data == "topup_stars")
def topup_stars(call):
    bot.answer_callback_query(call.id, "Поки що не доступно", show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data == "topup_card")
def topup_card(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"Яку сумму бажаєте закинути? (Мінімум {MIN_TOPUP}₴)",
    )
    bot.register_next_step_handler(msg, get_amount)


def get_amount(message):
    text = (message.text or "").replace(",", ".").strip()
    try:
        amount = float(text)
    except ValueError:
        amount = None

    if amount is None or amount < MIN_TOPUP:
        msg = bot.send_message(
            message.chat.id,
            f"Введіть число. Мінімум {MIN_TOPUP}₴",
        )
        bot.register_next_step_handler(msg, get_amount)
        return

    # нова заявка очікує квитанцію
    cur.execute(
        "UPDATE topups SET status = 'cancelled' "
        "WHERE user_id = ? AND status = 'waiting_receipt'",
        (message.from_user.id,),
    )
    cur.execute(
        "INSERT INTO topups (user_id, amount, status) VALUES (?, ?, 'waiting_receipt')",
        (message.from_user.id, amount),
    )
    db.commit()

    bot.send_message(
        message.chat.id,
        "Поповнення:\n"
        f"Сумма поповнення: {fmt(amount)}₴\n"
        f"До сплати: {fmt(amount)}₴\n\n"
        f"{CARD}\n\n"
        "Обов'язково після надсилання кидайте сюди квитанцію!",
    )


# ---------- Квитанція -> адміну ----------
@bot.message_handler(content_types=["photo", "document"])
def receipt(message):
    user_id = message.from_user.id
    cur.execute(
        "SELECT id, amount FROM topups "
        "WHERE user_id = ? AND status = 'waiting_receipt' "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    row = cur.fetchone()
    if row is None:
        return  # немає активної заявки - ігноруємо

    topup_id, amount = row
    cur.execute("UPDATE topups SET status = 'pending' WHERE id = ?", (topup_id,))
    db.commit()

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Прийняти", callback_data=f"ok_{topup_id}"),
        types.InlineKeyboardButton("❌ Відхилити", callback_data=f"no_{topup_id}"),
    )
    caption = (
        f"Нове поповнення #{topup_id}\n"
        f"Користувач: {user_id}\n"
        f"Сумма: {fmt(amount)}₴"
    )

    if message.content_type == "photo":
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, reply_markup=kb)
    else:
        bot.send_document(ADMIN_ID, message.document.file_id, caption=caption, reply_markup=kb)

    bot.send_message(message.chat.id, "Квитанцію отримано. Очікуйте підтвердження ⏳")


# ---------- Рішення адміна ----------
@bot.callback_query_handler(func=lambda c: c.data.startswith(("ok_", "no_")))
def admin_decision(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Немає доступу")
        return

    action, topup_id = call.data.split("_")
    topup_id = int(topup_id)

    cur.execute("SELECT user_id, amount, status FROM topups WHERE id = ?", (topup_id,))
    row = cur.fetchone()
    if row is None or row[2] != "pending":
        bot.answer_callback_query(call.id, "Вже оброблено")
        return

    user_id, amount, _ = row

    if action == "ok":
        get_user(user_id)
        cur.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount, user_id))
        cur.execute("UPDATE topups SET status = 'approved' WHERE id = ?", (topup_id,))
        db.commit()
        result = "✅ Прийнято"
        bot.send_message(user_id, f"✅ Поповнення на {fmt(amount)}₴ зараховано!")
    else:
        cur.execute("UPDATE topups SET status = 'rejected' WHERE id = ?", (topup_id,))
        db.commit()
        result = "❌ Відхилено"
        bot.send_message(user_id, f"❌ Поповнення на {fmt(amount)}₴ відхилено.")

    bot.edit_message_caption(
        f"Поповнення #{topup_id}\nСумма: {fmt(amount)}₴\n\n{result}",
        call.message.chat.id,
        call.message.message_id,
    )
    bot.answer_callback_query(call.id, result)


print("Бота запущено")
bot.infinity_polling()
