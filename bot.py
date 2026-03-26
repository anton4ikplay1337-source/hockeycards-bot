import telebot
from telebot import types
import sqlite3
import random
import json
from datetime import datetime, timedelta
import os
import time
import threading
import shutil
from flask import Flask

# ============ НАСТРОЙКИ (ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ) ============
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Получаем список админов из переменной окружения (через запятую)
admin_ids_str = os.environ.get('ADMIN_IDS', '123456789')
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(',')]

# Для обратной совместимости
if 'ADMIN_ID' in os.environ:
    old_admin = int(os.environ.get('ADMIN_ID'))
    if old_admin not in ADMIN_IDS:
        ADMIN_IDS.append(old_admin)
# ===================================================================

bot = telebot.TeleBot(TOKEN)

# Словари для временных данных
temp_card_data = {}
last_open_time = {}
user_collection_page = {}

# ============ РЕДКОСТИ КАРТОЧЕК ============
RARITIES = {
    'common': {'name': 'Обычная', 'emoji': '⬜', 'chance': 45, 'icon': '🃏'},
    'rare': {'name': 'Редкая', 'emoji': '🔵', 'chance': 25, 'icon': '⭐'},
    'epic': {'name': 'Эпическая', 'emoji': '🟣', 'chance': 15, 'icon': '✨'},
    'mythical': {'name': 'Мифическая', 'emoji': '🔴', 'chance': 10, 'icon': '🐉'},
    'legendary': {'name': 'Легендарная', 'emoji': '🟡', 'chance': 5, 'icon': '👑'}
}

# ============ БАЗА ДАННЫХ ============
def init_db():
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cards (
        card_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        team TEXT,
        country TEXT,
        rarity TEXT,
        image_path TEXT,
        added_by INTEGER,
        added_date TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        last_card_time TEXT DEFAULT NULL,
        cards_opened INTEGER DEFAULT 0,
        total_cards INTEGER DEFAULT 0
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_cards (
        user_id INTEGER,
        card_id INTEGER,
        opened_date TEXT,
        PRIMARY KEY (user_id, card_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )
    ''')
    
    conn.commit()
    conn.close()

def update_db_users():
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_card_time TEXT DEFAULT NULL")
        print("✅ Добавлен столбец last_card_time")
    except:
        pass
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN cards_opened INTEGER DEFAULT 0")
        print("✅ Добавлен столбец cards_opened")
    except:
        pass
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN total_cards INTEGER DEFAULT 0")
        print("✅ Добавлен столбец total_cards")
    except:
        pass
    
    try:
        cursor.execute("SELECT user_id FROM admins")
        db_admins = cursor.fetchall()
        for admin in db_admins:
            if admin[0] not in ADMIN_IDS:
                ADMIN_IDS.append(admin[0])
        print(f"👑 Загружено {len(ADMIN_IDS)} админов")
    except:
        pass
    
    conn.commit()
    conn.close()

def register_user(user_id, username):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

# ============ АВТОМАТИЧЕСКИЙ БЭКАП ============
def backup_database():
    try:
        if os.path.exists('hockey_cards.db'):
            if not os.path.exists('backups'):
                os.makedirs('backups')
            
            backup_name = f"backups/hockey_cards_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2('hockey_cards.db', backup_name)
            print(f"✅ Создан бэкап: {backup_name}")
            
            backups = sorted([f for f in os.listdir('backups') if f.startswith('hockey_cards_backup_')])
            for old_backup in backups[:-10]:
                os.remove(os.path.join('backups', old_backup))
    except Exception as e:
        print(f"⚠️ Ошибка бэкапа: {e}")

def auto_backup_loop():
    while True:
        time.sleep(86400)
        backup_database()

def auto_save_loop():
    while True:
        time.sleep(300)
        try:
            conn = sqlite3.connect('hockey_cards.db')
            conn.commit()
            conn.close()
            print("💾 Автосохранение выполнено")
        except:
            pass

backup_thread = threading.Thread(target=auto_backup_loop, daemon=True)
backup_thread.start()
save_thread = threading.Thread(target=auto_save_loop, daemon=True)
save_thread.start()

# ============ ФУНКЦИИ ДЛЯ КД ============
def can_open_card(user_id):
    if user_id in ADMIN_IDS:
        return True, None, 0
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT last_card_time, cards_opened FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return True, None, 0
    
    try:
        last_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
    except:
        return True, None, 0
    
    next_available = last_time + timedelta(hours=2)
    now = datetime.now()
    cards_opened = result[1] if result[1] else 0
    
    if now >= next_available:
        return True, None, cards_opened
    else:
        wait_time = next_available - now
        hours = int(wait_time.total_seconds() // 3600)
        minutes = int((wait_time.total_seconds() % 3600) // 60)
        return False, f"{hours}ч {minutes}м", cards_opened

def update_card_time(user_id):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("UPDATE users SET last_card_time = ?, cards_opened = cards_opened + 1 WHERE user_id = ?", (now, user_id))
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT cards_opened FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def add_card_to_db(name, team, country, rarity, image_path, added_by):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO cards (name, team, country, rarity, image_path, added_by, added_date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (name, team, country, rarity, image_path, added_by, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    card_id = cursor.lastrowid
    conn.close()
    return card_id

def get_random_card():
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cards ORDER BY RANDOM() LIMIT 1")
    card = cursor.fetchone()
    conn.close()
    return card

def get_card_by_id(card_id):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,))
    card = cursor.fetchone()
    conn.close()
    return card

def save_user_card(user_id, card_id):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO user_cards (user_id, card_id, opened_date) VALUES (?, ?, ?)",
                      (user_id, card_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    except:
        pass
    conn.close()

def get_user_collection_count(user_id):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_user_collection(user_id, offset=0, limit=10):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT c.* FROM cards c
    JOIN user_cards uc ON c.card_id = uc.card_id
    WHERE uc.user_id = ?
    ORDER BY uc.opened_date DESC
    LIMIT ? OFFSET ?
    ''', (user_id, limit, offset))
    cards = cursor.fetchall()
    conn.close()
    return cards

def get_total_cards_count():
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cards")
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ============ ФОРМИРОВАНИЕ КАРТОЧКИ ============
def get_card_text(card):
    card_id, name, team, country, rarity, image_path, added_by, added_date = card
    rarity_info = RARITIES[rarity]
    
    text = f"""{rarity_info['icon']} **{rarity_info['name']} КАРТОЧКА** {rarity_info['icon']}

🏒 **{name}**

🏆 **Команда:** {team}
🌍 **Страна:** {country}
💎 **Редкость:** {rarity_info['emoji']} {rarity_info['name']}
🆔 **ID:** #{card_id}

✨ Удачи в коллекционировании!"""
    return text

def get_card_keyboard(card_id, user_id):
    """Клавиатура для отдельной карточки"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_cards WHERE user_id = ? AND card_id = ?", (user_id, card_id))
    has_card = cursor.fetchone() is not None
    conn.close()
    
    if has_card:
        btn_collect = types.InlineKeyboardButton(text="✅ В коллекции", callback_data="already_collected")
    else:
        btn_collect = types.InlineKeyboardButton(text="📥 В коллекцию", callback_data=f"collect_{card_id}")
    
    btn_share = types.InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_{card_id}")
    btn_back = types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    keyboard.add(btn_collect, btn_share, btn_back)
    return keyboard

# ============ ИНЛАЙН-МЕНЮ ============
def main_menu_keyboard():
    """Главное меню с инлайн-кнопками"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_open = types.InlineKeyboardButton(text="🎴 Открыть карточку", callback_data="open_card")
    btn_collection = types.InlineKeyboardButton(text="📚 Моя коллекция", callback_data="show_collection_0")
    btn_stats = types.InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")
    btn_rarities = types.InlineKeyboardButton(text="💎 Редкости", callback_data="show_rarities")
    
    # Кнопка для админов
    if message_from_user_id_in_admin():
        btn_admin = types.InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin_panel")
        keyboard.add(btn_open, btn_collection, btn_stats, btn_rarities, btn_admin)
    else:
        keyboard.add(btn_open, btn_collection, btn_stats, btn_rarities)
    
    return keyboard

def message_from_user_id_in_admin():
    """Заглушка для проверки, будет заменено в обработчиках"""
    return False

def back_to_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main"))
    return keyboard

# ============ ОБРАБОТЧИКИ ============
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "user"
    
    register_user(user_id, username)
    cards_opened = get_user_stats(user_id)
    collection_count = get_user_collection_count(user_id)
    total_cards = get_total_cards_count()
    
    is_admin = "👑 Вы администратор!" if user_id in ADMIN_IDS else ""
    
    welcome_text = f"""🏒 **ХОККЕЙНЫЕ КАРТОЧКИ КХЛ**

📇 **Добро пожаловать!** {is_admin}

🎴 **Что ты можешь делать:**
• Открывать новые карточки (КД 2 часа)
• Собирать коллекцию
• Смотреть свою статистику
• Узнавать о редкостях карточек

📊 **Твоя статистика:**
• 🎴 Открыто карточек: {cards_opened}
• 📚 В коллекции: {collection_count} / {total_cards}
• ⏰ КД на открытие: 2 часа

💡 Нажми на кнопки ниже!"""
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_open = types.InlineKeyboardButton(text="🎴 Открыть карточку", callback_data="open_card")
    btn_collection = types.InlineKeyboardButton(text="📚 Моя коллекция", callback_data="show_collection_0")
    btn_stats = types.InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")
    btn_rarities = types.InlineKeyboardButton(text="💎 Редкости", callback_data="show_rarities")
    
    if user_id in ADMIN_IDS:
        btn_admin = types.InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin_panel")
        keyboard.add(btn_open, btn_collection, btn_stats, btn_rarities, btn_admin)
    else:
        keyboard.add(btn_open, btn_collection, btn_stats, btn_rarities)
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main(call):
    user_id = call.from_user.id
    cards_opened = get_user_stats(user_id)
    collection_count = get_user_collection_count(user_id)
    total_cards = get_total_cards_count()
    
    is_admin = "👑 Вы администратор!" if user_id in ADMIN_IDS else ""
    
    welcome_text = f"""🏒 **ХОККЕЙНЫЕ КАРТОЧКИ КХЛ**

📇 **Главное меню** {is_admin}

📊 **Твоя статистика:**
• 🎴 Открыто карточек: {cards_opened}
• 📚 В коллекции: {collection_count} / {total_cards}
• ⏰ КД на открытие: 2 часа

💡 Выбери действие:"""
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_open = types.InlineKeyboardButton(text="🎴 Открыть карточку", callback_data="open_card")
    btn_collection = types.InlineKeyboardButton(text="📚 Моя коллекция", callback_data="show_collection_0")
    btn_stats = types.InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")
    btn_rarities = types.InlineKeyboardButton(text="💎 Редкости", callback_data="show_rarities")
    
    if user_id in ADMIN_IDS:
        btn_admin = types.InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin_panel")
        keyboard.add(btn_open, btn_collection, btn_stats, btn_rarities, btn_admin)
    else:
        keyboard.add(btn_open, btn_collection, btn_stats, btn_rarities)
    
    bot.edit_message_text(welcome_text, call.message.chat.id, call.message.message_id, 
                          reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "open_card")
def open_card_callback(call):
    user_id = call.from_user.id
    now_time = time.time()
    
    if user_id in last_open_time:
        if now_time - last_open_time[user_id] < 5:
            bot.answer_callback_query(call.id, "⏳ Подожди 5 секунд перед следующим открытием!", show_alert=True)
            return
    last_open_time[user_id] = now_time
    
    can_open, wait_time, cards_opened = can_open_card(user_id)
    
    if not can_open:
        bot.answer_callback_query(call.id, f"⏰ КД 2 часа! Следующая карточка через {wait_time}", show_alert=True)
        return
    
    card = get_random_card()
    
    if not card:
        bot.edit_message_text("❌ В базе пока нет карточек! Обратитесь к администратору.", 
                             call.message.chat.id, call.message.message_id,
                             reply_markup=back_to_menu_keyboard())
        return
    
    update_card_time(user_id)
    save_user_card(user_id, card[0])
    
    card_text = get_card_text(card)
    keyboard = get_card_keyboard(card[0], user_id)
    
    next_time = datetime.now() + timedelta(hours=2)
    next_time_str = next_time.strftime('%H:%M:%S')
    
    bot.edit_message_text(card_text + f"\n\n⏰ Следующая карточка через **2 часа** (после {next_time_str})",
                         call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "show_stats")
def show_stats_callback(call):
    user_id = call.from_user.id
    cards_opened = get_user_stats(user_id)
    collection_count = get_user_collection_count(user_id)
    total_cards = get_total_cards_count()
    
    cards = get_user_collection(user_id, 0, 1000)
    rarity_counts = {'common': 0, 'rare': 0, 'epic': 0, 'mythical': 0, 'legendary': 0}
    for card in cards:
        rarity_counts[card[4]] += 1
    
    collection_percent = (collection_count / total_cards * 100) if total_cards > 0 else 0
    
    text = f"📊 **ВАША СТАТИСТИКА**\n\n"
    text += f"🎴 **Открыто карточек:** {cards_opened}\n"
    text += f"📚 **В коллекции:** {collection_count} / {total_cards}\n"
    text += f"📈 **Прогресс:** {collection_percent:.1f}%\n\n"
    text += f"💎 **Коллекция по редкостям:**\n"
    text += f"⬜ Обычные: {rarity_counts['common']}\n"
    text += f"🔵 Редкие: {rarity_counts['rare']}\n"
    text += f"🟣 Эпические: {rarity_counts['epic']}\n"
    text += f"🔴 Мифические: {rarity_counts['mythical']}\n"
    text += f"🟡 Легендарные: {rarity_counts['legendary']}\n\n"
    text += f"⏰ **КД на открытие:** 2 часа"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "show_rarities")
def show_rarities_callback(call):
    text = f"💎 **РЕДКОСТИ КАРТОЧЕК**\n\n"
    
    for key, rarity in RARITIES.items():
        text += f"{rarity['emoji']} **{rarity['name']}**\n"
        text += f"   Шанс выпадения: {rarity['chance']}%\n"
        text += f"   {rarity['icon']} {rarity['icon']} {rarity['icon']}\n\n"
    
    text += f"✨ **Чем реже карточка, тем она ценнее!**\n"
    text += f"🔴 Мифические карточки выпадают с шансом 10%!\n"
    text += f"🟡 Легендарные карточки выпадают с шансом 5%!"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('show_collection_'))
def show_collection_callback(call):
    user_id = call.from_user.id
    page = int(call.data.split('_')[2]) if len(call.data.split('_')) > 2 else 0
    items_per_page = 10
    
    total_cards = get_user_collection_count(user_id)
    total_pages = (total_cards + items_per_page - 1) // items_per_page
    
    if total_cards == 0:
        bot.edit_message_text("📭 **Ваша коллекция пуста!**\n\nНажми **🎴 Открыть карточку** чтобы начать собирать!",
                             call.message.chat.id, call.message.message_id,
                             reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')
        return
    
    cards = get_user_collection(user_id, page * items_per_page, items_per_page)
    
    text = f"📚 **ВАША КОЛЛЕКЦИЯ** (стр. {page + 1}/{total_pages})\n\n"
    
    for card in cards:
        rarity_info = RARITIES[card[4]]
        text += f"{rarity_info['emoji']} **{card[1]}** ({card[2]}) — {rarity_info['name']}\n"
        text += f"   🆔 #{card[0]}\n\n"
    
    # Создаем клавиатуру для пагинации
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    
    if page > 0:
        keyboard.add(types.InlineKeyboardButton(text="◀️ Предыдущая", callback_data=f"show_collection_{page-1}"))
    
    keyboard.add(types.InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main"))
    
    if page < total_pages - 1:
        keyboard.add(types.InlineKeyboardButton(text="Следующая ▶️", callback_data=f"show_collection_{page+1}"))
    
    # Кнопка для просмотра конкретной карточки
    if cards:
        view_keyboard = types.InlineKeyboardMarkup(row_width=2)
        for card in cards[:5]:
            view_keyboard.add(types.InlineKeyboardButton(text=f"👀 {card[1]}", callback_data=f"view_card_{card[0]}"))
        view_keyboard.add(types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"show_collection_{page}"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=view_keyboard, parse_mode='Markdown')
    else:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_card_'))
def view_card(call):
    card_id = int(call.data.split('_')[2])
    user_id = call.from_user.id
    card = get_card_by_id(card_id)
    
    if card:
        card_text = get_card_text(card)
        keyboard = get_card_keyboard(card_id, user_id)
        bot.edit_message_text(card_text, call.message.chat.id, call.message.message_id,
                             reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "already_collected")
def already_collected(call):
    bot.answer_callback_query(call.id, "✅ Эта карточка уже есть в вашей коллекции!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('collect_'))
def collect_card_callback(call):
    user_id = call.from_user.id
    card_id = int(call.data.split('_')[1])
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_cards WHERE user_id = ? AND card_id = ?", (user_id, card_id))
    exists = cursor.fetchone()
    
    if exists:
        bot.answer_callback_query(call.id, "⚠️ Эта карточка уже есть в вашей коллекции!", show_alert=True)
    else:
        save_user_card(user_id, card_id)
        bot.answer_callback_query(call.id, "✅ Карточка добавлена в коллекцию!", show_alert=True)
        
        # Обновляем кнопки
        card = get_card_by_id(card_id)
        if card:
            card_text = get_card_text(card)
            keyboard = get_card_keyboard(card_id, user_id)
            bot.edit_message_text(card_text, call.message.chat.id, call.message.message_id,
                                 reply_markup=keyboard, parse_mode='Markdown')
    
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('share_'))
def share_card_callback(call):
    card_id = int(call.data.split('_')[1])
    card = get_card_by_id(card_id)
    
    if card:
        rarity_info = RARITIES[card[4]]
        share_text = f"🏒 Хоккейная карточка\n\n{rarity_info['icon']} {card[1]} ({card[2]}) — {rarity_info['name']}\n🌍 {card[3]}\n🆔 #{card_id}\n\nПолучи свою карточку!"
        bot.answer_callback_query(call.id, "Карточка скопирована!", show_alert=True)
        bot.send_message(call.message.chat.id, share_text, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel_callback(call):
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_add_card = types.InlineKeyboardButton(text="➕ Добавить карточку", callback_data="add_card_start")
    btn_cards_list = types.InlineKeyboardButton(text="📋 Список карточек", callback_data="cards_list")
    btn_backup = types.InlineKeyboardButton(text="💾 Создать бэкап", callback_data="backup_db")
    btn_reset_cd = types.InlineKeyboardButton(text="⏰ Сбросить КД себе", callback_data="reset_my_cd")
    btn_stats = types.InlineKeyboardButton(text="📊 Статистика БД", callback_data="db_stats")
    btn_admins = types.InlineKeyboardButton(text="👑 Список админов", callback_data="list_admins")
    btn_back = types.InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")
    keyboard.add(btn_add_card, btn_cards_list, btn_backup, btn_reset_cd, btn_stats, btn_admins, btn_back)
    
    bot.edit_message_text("🔧 **АДМИН-ПАНЕЛЬ**\n\nВыберите действие:", 
                         call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "reset_my_cd")
def reset_my_cd_callback(call):
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_card_time = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    bot.answer_callback_query(call.id, "✅ Ваш КД сброшен! Можете открыть новую карточку.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "backup_db")
def backup_db_callback(call):
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    try:
        if not os.path.exists('backups'):
            os.makedirs('backups')
        
        backup_name = f"backups/hockey_cards_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2('hockey_cards.db', backup_name)
        
        with open(backup_name, 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption=f"✅ Бэкап создан: {backup_name}")
        
        bot.answer_callback_query(call.id, "✅ Бэкап создан и отправлен!", show_alert=True)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {e}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "db_stats")
def db_stats_callback(call):
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    
    db_size = os.path.getsize('hockey_cards.db') / 1024
    
    cursor.execute("SELECT COUNT(*) FROM cards")
    total_cards = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM user_cards")
    total_collections = cursor.fetchone()[0]
    
    conn.close()
    
    text = f"📊 **СТАТИСТИКА БАЗЫ ДАННЫХ**\n\n"
    text += f"💾 **Размер БД:** {db_size:.1f} KB\n"
    text += f"🃏 **Всего карточек:** {total_cards}\n"
    text += f"👥 **Всего игроков:** {total_users}\n"
    text += f"📚 **Всего в коллекциях:** {total_collections}"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "list_admins")
def list_admins_callback(call):
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    text = "👑 **СПИСОК АДМИНОВ**\n\n"
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    
    for admin_id in ADMIN_IDS:
        cursor.execute("SELECT username FROM users WHERE user_id = ?", (admin_id,))
        result = cursor.fetchone()
        username = result[0] if result else str(admin_id)
        text += f"• @{username} (ID: {admin_id})\n"
    
    conn.close()
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "cards_list")
def cards_list_callback(call):
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT card_id, name, team, rarity FROM cards ORDER BY card_id")
    cards = cursor.fetchall()
    conn.close()
    
    if not cards:
        bot.edit_message_text("📭 В базе нет карточек.", call.message.chat.id, call.message.message_id,
                             reply_markup=back_to_menu_keyboard())
        return
    
    text = "📋 **СПИСОК КАРТОЧЕК**\n\n"
    for card in cards:
        rarity_info = RARITIES[card[3]]
        text += f"{rarity_info['emoji']} **ID:{card[0]}** {card[1]} ({card[2]}) — {rarity_info['name']}\n"
    
    # Если текст слишком длинный, отправляем как есть
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text="🗑️ Удалить карточку", callback_data="delete_card_menu"))
    keyboard.add(types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "delete_card_menu")
def delete_card_menu(call):
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    msg = bot.send_message(call.message.chat.id, "🗑️ Введите **ID карточки** для удаления:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_delete_card, call.message.chat.id, call.message.message_id)

def process_delete_card(message, chat_id, msg_id):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    try:
        card_id = int(message.text.strip())
        
        conn = sqlite3.connect('hockey_cards.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name, image_path FROM cards WHERE card_id = ?", (card_id,))
        card = cursor.fetchone()
        
        if not card:
            bot.send_message(message.chat.id, f"❌ Карточка с ID {card_id} не найдена!")
            return
        
        if card[1] and os.path.exists(card[1]):
            os.remove(card[1])
        
        cursor.execute("DELETE FROM cards WHERE card_id = ?", (card_id,))
        cursor.execute("DELETE FROM user_cards WHERE card_id = ?", (card_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Карточка **{card[0]}** удалена!")
        
        # Возвращаемся к админ-панели
        admin_panel_callback(message)
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректный ID карточки!")

@bot.callback_query_handler(func=lambda call: call.data == "add_card_start")
def add_card_start_callback(call):
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    temp_card_data[user_id] = {}
    msg = bot.send_message(call.message.chat.id, "📝 Введите **имя игрока**:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_card_name, call.message.chat.id, call.message.message_id)

def process_card_name(message, chat_id, msg_id):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    if user_id not in temp_card_data:
        temp_card_data[user_id] = {}
    
    temp_card_data[user_id]['name'] = message.text.strip()
    msg = bot.send_message(chat_id, "🏆 Введите **команду**:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_card_team, chat_id, msg_id)

def process_card_team(message, chat_id, msg_id):
    user_id = message.from_user.id
    temp_card_data[user_id]['team'] = message.text.strip()
    msg = bot.send_message(chat_id, "🌍 Введите **страну**:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_card_country, chat_id, msg_id)

def process_card_country(message, chat_id, msg_id):
    user_id = message.from_user.id
    temp_card_data[user_id]['country'] = message.text.strip()
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for key, rarity in RARITIES.items():
        btn = types.InlineKeyboardButton(
            text=f"{rarity['emoji']} {rarity['name']}",
            callback_data=f"set_rarity_{key}"
        )
        keyboard.add(btn)
    
    bot.send_message(chat_id, "💎 Выберите **редкость** карточки:", reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_rarity_'))
def process_card_rarity_callback(call):
    user_id = call.from_user.id
    rarity = call.data.split('_')[2]
    
    if user_id not in temp_card_data:
        temp_card_data[user_id] = {}
    
    temp_card_data[user_id]['rarity'] = rarity
    
    bot.edit_message_text(
        f"✅ Редкость выбрана: {RARITIES[rarity]['emoji']} {RARITIES[rarity]['name']}\n\n📸 Теперь отправьте **изображение** карточки или нажмите любую кнопку чтобы пропустить:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )
    
    msg = bot.send_message(call.message.chat.id, "🖼️ Отправьте фото игрока (или нажмите любую кнопку):")
    bot.register_next_step_handler(msg, process_card_image_final, call.message.chat.id, call.message.message_id)

def process_card_image_final(message, chat_id, msg_id):
    user_id = message.from_user.id
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        if not os.path.exists('card_images'):
            os.makedirs('card_images')
        
        image_name = f"card_{user_id}_{int(time.time())}.jpg"
        image_path = os.path.join('card_images', image_name)
        
        with open(image_path, 'wb') as f:
            f.write(downloaded_file)
        
        temp_card_data[user_id]['image_path'] = image_path
    else:
        temp_card_data[user_id]['image_path'] = None
    
    data = temp_card_data[user_id]
    card_id = add_card_to_db(
        name=data['name'],
        team=data['team'],
        country=data['country'],
        rarity=data['rarity'],
        image_path=data['image_path'],
        added_by=user_id
    )
    
    del temp_card_data[user_id]
    
    card = get_card_by_id(card_id)
    card_text = get_card_text(card)
    
    bot.send_message(chat_id, f"✅ **Карточка успешно добавлена!**\n\n{card_text}\n🆔 ID: {card_id}", parse_mode='Markdown')
    
    # Возвращаемся в админ-панель
    admin_panel_callback(message)

# ============ ВЕБ-СЕРВЕР ДЛЯ RENDER ============
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "🏒 Hockey Cards Bot is running on Render! 🎴"

@flask_app.route('/ping')
def ping():
    return "pong"

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask, daemon=True).start()
print("🌐 Веб-сервер запущен на порту 8080")

# ============ ЗАПУСК ============
if __name__ == '__main__':
    init_db()
    update_db_users()
    print("🤖 Бот хоккейных карточек запущен!")
    print("💎 Редкости: Обычная (45%), Редкая (25%), Эпическая (15%), Мифическая (10%), Легендарная (5%)")
    print("⏰ КД на открытие: 2 ЧАСА")
    print(f"👑 Количество админов: {len(ADMIN_IDS)}")
    print("🎮 Все кнопки - инлайн!")
    print("📚 Добавлен просмотр всех карточек с пагинацией")
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")
            time.sleep(10)
