import os
import sqlite3
import telebot
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    from config import TOKEN  # локальний файл для Pydroid3

ADMIN_ID = 7660211311
CARD = os.environ.get("CARD", "4874 0700 6372 5947")
DB_PATH = os.environ.get("DB_PATH", "bot.db")
SUPPORT = "@derunovich"

MIN_TOPUP = 10                 # мінімум поповнення на карту, грн
MIN_STARS = 1                  # мінімум поповнення зірками
MIN_SELL = 10_000_000          # мінімум продажу, віртуальна валюта
UAH_PER_MILLION = 3            # поповнення: 30грн = 10.000.000

# Курси калькулятора
CALC_UAH_PER_MILLION = 3       # 3 грн = 1.000.000 валюти
CALC_STARS_PER_MILLION = 5     # 5 зірок = 1.000.000 валюти
CALC_SELL_UAH_PER_MILLION = 1.5  # 1.000.000 валюти = 1.50 грн

SELL_TABLE = [
    (1_000_000, 3),
    (5_000_000, 15),
    (10_000_000, 30),
    (50_000_000, 130),
    (100_000_000, 280),
]

bot = telebot.TeleBot(TOKEN)

# ---------- База даних ----------
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
db = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    money REAL DEFAULT 0,
    stars INTEGER DEFAULT 0,
    total_topped_up REAL DEFAULT 0
)
""")
cur.execute("PRAGMA table_info(users)")
cols = [r[1] for r in cur.fetchall()]
if "stars" not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN stars INTEGER DEFAULT 0")
if "total_topped_up" not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN total_topped_up REAL DEFAULT 0")

cur.execute("""
CREATE TABLE IF NOT EXISTS topups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    status TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS sells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    virtual INTEGER,
    payout REAL,
    cost REAL,
    requisites TEXT,
    status TEXT
)
""")
db.commit()


def get_user(user_id):
    cur.execute(
        "SELECT money, stars, total_topped_up FROM users WHERE user_id = ?",
        (user_id,),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        db.commit()
        return 0, 0, 0
    return row


def fmt(n):
    return f"{n:g}"


def big(n):
    """10000000 -> 10.000.000"""
    return f"{int(n):,}".replace(",", ".")


def sell_payout(virtual):
    if virtual >= 100_000_000:
        rate = 2.8
    elif virtual >= 50_000_000:
        rate = 2.6
    else:
        rate = 3
    return round(virtual / 1_000_000 * rate, 2)


def sell_cost(virtual):
    return round(virtual / 1_000_000 * UAH_PER_MILLION, 2)


# ---------- Клавіатури ----------
BTN_PROFILE = "✈️Профіль"
BTN_WALLET = "💸 Гаманець"
BTN_CALC = "🧮 Калькулятор"
BTN_SETTINGS = "⚙️ Налаштування"
BTN_TOPUP = "ПОПОВНИТИ"
BTN_SELL = "ПРОДАТИ"
BTN_BACK = "⬅️ Назад"
BTN_UAH_TO_CUR = "грн -> валюта"
BTN_CUR_TO_UAH = "Валюта -> грн"
BTN_STARS_TO_CUR = "Зірки -> валюта"
ALL_BUTTONS = {
    BTN_PROFILE, BTN_WALLET, BTN_CALC, BTN_SETTINGS,
    BTN_TOPUP, BTN_SELL, BTN_BACK,
    BTN_UAH_TO_CUR, BTN_CUR_TO_UAH, BTN_STARS_TO_CUR,
}


def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(BTN_PROFILE, BTN_WALLET)
    kb.add(BTN_CALC, BTN_SETTINGS)
    return kb


def wallet_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(BTN_TOPUP, BTN_SELL)
    kb.add(BTN_BACK)
    return kb


def calc_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(BTN_UAH_TO_CUR, BTN_CUR_TO_UAH)
    kb.add(BTN_STARS_TO_CUR)
    kb.add(BTN_BACK)
    return kb


def cancel_if_menu(message):
    """Якщо натиснули кнопку меню замість введення - скасовуємо."""
    if message.text in ALL_BUTTONS:
        bot.send_message(message.chat.id, "Скасовано.", reply_markup=main_menu())
        return True
    return False


@bot.message_handler(commands=["start"])
def start(message):
    get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "Вітаю! Обери розділ меню 👇",
        reply_markup=main_menu(),
    )


@bot.message_handler(func=lambda m: m.text == BTN_BACK)
def back(message):
    bot.send_message(message.chat.id, "Головне меню 👇", reply_markup=main_menu())


# ---------- Адмін: ручне нарахування ----------
@bot.message_handler(commands=["add"])
def admin_add(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = (message.text or "").split()
    try:
        user_id = int(parts[1])
        amount = float(parts[2].replace(",", "."))
    except (IndexError, ValueError):
        bot.send_message(message.chat.id, "Формат: /add айді_користувача сума")
        return
    get_user(user_id)
    cur.execute(
        "UPDATE users SET money = money + ?, total_topped_up = total_topped_up + ? "
        "WHERE user_id = ?",
        (amount, amount, user_id),
    )
    db.commit()
    bot.send_message(message.chat.id, f"Додано {fmt(amount)}₴ користувачу {user_id}")


# ---------- Профіль ----------
@bot.message_handler(func=lambda m: m.text == BTN_PROFILE)
def profile(message):
    get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"✈️Профіль\n\n🆔: {message.from_user.id}",
    )


# ---------- Налаштування ----------
@bot.message_handler(func=lambda m: m.text == BTN_SETTINGS)
def settings(message):
    bot.send_message(message.chat.id, f"Підтримка: {SUPPORT}")


# ---------- Гаманець ----------
@bot.message_handler(func=lambda m: m.text == BTN_WALLET)
def wallet(message):
    money, stars, _ = get_user(message.from_user.id)
    game = int(money / UAH_PER_MILLION * 1_000_000)  # 30грн = 10.000.000
    bot.send_message(
        message.chat.id,
        f"Гроші: {fmt(money)}₴\n\n"
        f"Зірки: {stars}\n\n"
        f"Ігрова валюта: {big(game)}",
        reply_markup=wallet_menu(),
    )


# ---------- Калькулятор ----------
@bot.message_handler(func=lambda m: m.text == BTN_CALC)
def calc(message):
    bot.send_message(
        message.chat.id,
        "Калькулятор - за допомогою якого ви дізнаєтеся курс валюти",
        reply_markup=calc_menu(),
    )


def parse_decimal(text):
    try:
        return float((text or "").replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def parse_int(text):
    t = (text or "").replace(".", "").replace(",", "").replace(" ", "")
    return int(t) if t.isdigit() else None


@bot.message_handler(func=lambda m: m.text == BTN_UAH_TO_CUR)
def calc_uah(message):
    msg = bot.send_message(message.chat.id, "Введіть суму в грн:")
    bot.register_next_step_handler(msg, calc_uah_result)


def calc_uah_result(message):
    if cancel_if_menu(message):
        return
    amount = parse_decimal(message.text)
    if amount is None or amount <= 0:
        msg = bot.send_message(message.chat.id, "Введіть число, наприклад 30")
        bot.register_next_step_handler(msg, calc_uah_result)
        return
    result = int(amount / CALC_UAH_PER_MILLION * 1_000_000)
    bot.send_message(message.chat.id, f"{fmt(amount)}грн = {big(result)} валюти")


@bot.message_handler(func=lambda m: m.text == BTN_CUR_TO_UAH)
def calc_cur(message):
    msg = bot.send_message(message.chat.id, "Введіть кількість валюти:")
    bot.register_next_step_handler(msg, calc_cur_result)


def calc_cur_result(message):
    if cancel_if_menu(message):
        return
    amount = parse_int(message.text)
    if amount is None or amount <= 0:
        msg = bot.send_message(message.chat.id, "Введіть число, наприклад 1000000")
        bot.register_next_step_handler(msg, calc_cur_result)
        return
    result = amount / 1_000_000 * CALC_SELL_UAH_PER_MILLION
    bot.send_message(message.chat.id, f"{big(amount)} валюти = {fmt(round(result, 2))}грн")


@bot.message_handler(func=lambda m: m.text == BTN_STARS_TO_CUR)
def calc_stars(message):
    msg = bot.send_message(message.chat.id, "Введіть кількість зірок:")
    bot.register_next_step_handler(msg, calc_stars_result)


def calc_stars_result(message):
    if cancel_if_menu(message):
        return
    amount = parse_decimal(message.text)
    if amount is None or amount <= 0:
        msg = bot.send_message(message.chat.id, "Введіть число, наприклад 5")
        bot.register_next_step_handler(msg, calc_stars_result)
        return
    result = int(amount / CALC_STARS_PER_MILLION * 1_000_000)
    bot.send_message(message.chat.id, f"{fmt(amount)}⭐️ = {big(result)} валюти")


# ---------- ПОПОВНИТИ ----------
@bot.message_handler(func=lambda m: m.text == BTN_TOPUP)
def topup(message):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("💳 На карту", callback_data="topup_card"),
        types.InlineKeyboardButton("⭐️ Зірками", callback_data="topup_stars"),
    )
    bot.send_message(message.chat.id, "Поповнення\n\nОберіть спосіб:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "topup_card")
def topup_card(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"Яку сумму бажаєте закинути? (Мінімум {MIN_TOPUP}₴)",
    )
    bot.register_next_step_handler(msg, get_card_amount)


def get_card_amount(message):
    if cancel_if_menu(message):
        return
    amount = parse_decimal(message.text)
    if amount is None or amount < MIN_TOPUP:
        msg = bot.send_message(message.chat.id, f"Введіть число. Мінімум {MIN_TOPUP}₴")
        bot.register_next_step_handler(msg, get_card_amount)
        return

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


@bot.callback_query_handler(func=lambda c: c.data == "topup_stars")
def topup_stars(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"Скільки зірок бажаєте закинути? (Мінімум {MIN_STARS}⭐️)",
    )
    bot.register_next_step_handler(msg, get_stars_amount)


def get_stars_amount(message):
    if cancel_if_menu(message):
        return
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) < MIN_STARS:
        msg = bot.send_message(message.chat.id, f"Введіть ціле число. Мінімум {MIN_STARS}⭐️")
        bot.register_next_step_handler(msg, get_stars_amount)
        return

    stars = int(text)
    bot.send_invoice(
        message.chat.id,
        title="Поповнення зірками",
        description=f"Поповнення гаманця на {stars}⭐️",
        invoice_payload=f"stars_{stars}",
        provider_token="",
        currency="XTR",
        prices=[types.LabeledPrice(label="Зірки", amount=stars)],
    )


@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True)


@bot.message_handler(content_types=["successful_payment"])
def paid(message):
    stars = message.successful_payment.total_amount
    user_id = message.from_user.id
    get_user(user_id)
    cur.execute("UPDATE users SET stars = stars + ? WHERE user_id = ?", (stars, user_id))
    db.commit()
    bot.send_message(message.chat.id, f"✅ Поповнення на {stars}⭐️ зараховано!")
    bot.send_message(
        ADMIN_ID,
        f"⭐️ Поповнення зірками\nКористувач: {user_id}\nКількість: {stars}⭐️",
    )


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
        return

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


@bot.callback_query_handler(func=lambda c: c.data.startswith(("ok_", "no_")))
def topup_decision(call):
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
        cur.execute(
            "UPDATE users SET money = money + ?, total_topped_up = total_topped_up + ? "
            "WHERE user_id = ?",
            (amount, amount, user_id),
        )
        cur.execute("UPDATE topups SET status = 'approved' WHERE id = ?", (topup_id,))
        db.commit()
        result = "✅ Прийнято"
        virtual = int(amount / UAH_PER_MILLION * 1_000_000)
        bot.send_message(
            user_id,
            f"✅ Поповнення на {fmt(amount)}₴ зараховано!\n"
            f"Це {big(virtual)} віртуальної валюти.",
        )
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


# ---------- ПРОДАТИ ----------
@bot.message_handler(func=lambda m: m.text == BTN_SELL)
def sell(message):
    lines = "\n".join(f"{big(v)} = {p}грн" for v, p in SELL_TABLE)
    msg = bot.send_message(
        message.chat.id,
        f"Продажа:\n{lines}\n\n"
        f"Вкажіть суму у віртуальній валюті (мінімум {big(MIN_SELL)})",
    )
    bot.register_next_step_handler(msg, get_sell_amount)


def get_sell_amount(message):
    if cancel_if_menu(message):
        return
    virtual = parse_int(message.text)
    if virtual is None or virtual < MIN_SELL:
        msg = bot.send_message(message.chat.id, f"Введіть число. Мінімум {big(MIN_SELL)}")
        bot.register_next_step_handler(msg, get_sell_amount)
        return

    payout = sell_payout(virtual)
    cost = sell_cost(virtual)

    money, _, _ = get_user(message.from_user.id)
    if money < cost:
        bot.send_message(
            message.chat.id,
            f"Недостатньо коштів. Для продажу {big(virtual)} потрібно {fmt(cost)}₴ на балансі, "
            f"у вас {fmt(money)}₴.",
        )
        return

    cur.execute(
        "INSERT INTO sells (user_id, virtual, payout, cost, status) "
        "VALUES (?, ?, ?, ?, 'waiting_requisites')",
        (message.from_user.id, virtual, payout, cost),
    )
    sell_id = cur.lastrowid
    db.commit()

    msg = bot.send_message(
        message.chat.id,
        f"Сума до виведення: {fmt(payout)}грн\n\n"
        "Просимо ввести реквізити (карту та назва банку)",
    )
    bot.register_next_step_handler(msg, get_requisites, sell_id)


def get_requisites(message, sell_id):
    if cancel_if_menu(message):
        return
    requisites = (message.text or "").strip()
    if len(requisites) < 5:
        msg = bot.send_message(message.chat.id, "Введіть карту та назву банку")
        bot.register_next_step_handler(msg, get_requisites, sell_id)
        return

    cur.execute(
        "UPDATE sells SET requisites = ?, status = 'pending' WHERE id = ?",
        (requisites, sell_id),
    )
    db.commit()
    cur.execute("SELECT user_id, virtual, payout FROM sells WHERE id = ?", (sell_id,))
    user_id, virtual, payout = cur.fetchone()

    bot.send_message(message.chat.id, "Реквізити прийняті, очікуйте до 60 хвилин")

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Надіслав", callback_data=f"sent_{sell_id}"))
    bot.send_message(
        ADMIN_ID,
        f"Заявка на виведення #{sell_id} (користувач {user_id}, {big(virtual)})\n\n"
        f"Реквізити:\n{requisites}\n"
        f"Сумма виведення: {fmt(payout)}грн",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("sent_"))
def sell_sent(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Немає доступу")
        return

    sell_id = int(call.data.split("_")[1])
    cur.execute(
        "SELECT user_id, virtual, payout, cost, requisites, status FROM sells WHERE id = ?",
        (sell_id,),
    )
    row = cur.fetchone()
    if row is None or row[5] != "pending":
        bot.answer_callback_query(call.id, "Вже оброблено")
        return
    user_id, virtual, payout, cost, requisites, _ = row

    money, _, _ = get_user(user_id)
    if money < cost:
        bot.answer_callback_query(
            call.id, "У користувача вже недостатньо коштів на балансі", show_alert=True
        )
        return

    cur.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (cost, user_id))
    cur.execute("UPDATE sells SET status = 'done' WHERE id = ?", (sell_id,))
    db.commit()

    bot.edit_message_text(
        f"Заявка #{sell_id}\n\nРеквізити:\n{requisites}\n"
        f"Сумма виведення: {fmt(payout)}грн\n\n✅ Надіслано",
        call.message.chat.id,
        call.message.message_id,
    )
    bot.send_message(user_id, f"✅ Виплату {fmt(payout)}грн надіслано!")
    bot.answer_callback_query(call.id, "Готово")


print("Бота запущено")
bot.infinity_polling()
