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
TOKEN = os.environ.get('BOT_TOKEN', '8771956491:AAEM1HrlOvnjAS6L2VQZa5xvqsjG64jlhyc')

# Получаем список админов из переменной окружения (через запятую)
# Пример: "123456789,987654321,555555555"
admin_ids_str = os.environ.get('ADMIN_IDS', "5706071030,5286431840")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(',')]

# Для обратной совместимости (если используется старая переменная ADMIN_ID)
if 'ADMIN_ID' in os.environ:
    old_admin = int(os.environ.get('ADMIN_ID'))
    if old_admin not in ADMIN_IDS:
        ADMIN_IDS.append(old_admin)
# ===================================================================

bot = telebot.TeleBot(TOKEN)

# Словарь для временного хранения данных при добавлении карточки
temp_card_data = {}

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
    
    # Таблица карточек
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
    
    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        last_card_time TEXT DEFAULT NULL,
        cards_opened INTEGER DEFAULT 0,
        total_cards INTEGER DEFAULT 0
    )
    ''')
    
    # Таблица коллекции пользователя
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_cards (
        user_id INTEGER,
        card_id INTEGER,
        opened_date TEXT,
        PRIMARY KEY (user_id, card_id)
    )
    ''')
    
    # Таблица админов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )
    ''')
    
    conn.commit()
    conn.close()

def update_db_users():
    """Добавляет новые столбцы в существующую таблицу users"""
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
    
    # Загружаем админов из базы в память при запуске
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
    """Создает резервную копию базы данных"""
    try:
        if os.path.exists('hockey_cards.db'):
            if not os.path.exists('backups'):
                os.makedirs('backups')
            
            backup_name = f"backups/hockey_cards_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2('hockey_cards.db', backup_name)
            print(f"✅ Создан бэкап: {backup_name}")
            
            # Удаляем старые бэкапы (оставляем последние 10)
            backups = sorted([f for f in os.listdir('backups') if f.startswith('hockey_cards_backup_')])
            for old_backup in backups[:-10]:
                os.remove(os.path.join('backups', old_backup))
                print(f"🗑️ Удален старый бэкап: {old_backup}")
    except Exception as e:
        print(f"⚠️ Ошибка бэкапа: {e}")

def auto_backup_loop():
    """Запускает авто-бэкап каждые 24 часа"""
    while True:
        time.sleep(86400)  # 24 часа
        backup_database()

def auto_save_loop():
    """Принудительное сохранение каждые 5 минут"""
    while True:
        time.sleep(300)  # 5 минут
        try:
            conn = sqlite3.connect('hockey_cards.db')
            conn.commit()
            conn.close()
            print("💾 Автосохранение выполнено")
        except Exception as e:
            print(f"⚠️ Ошибка автосохранения: {e}")

# Запускаем фоновые процессы
backup_thread = threading.Thread(target=auto_backup_loop, daemon=True)
backup_thread.start()
save_thread = threading.Thread(target=auto_save_loop, daemon=True)
save_thread.start()
print("🔄 Авто-бэкап запущен (каждые 24 часа)")
print("💾 Автосохранение запущено (каждые 5 минут)")

# ============ ФУНКЦИИ ДЛЯ КД (2 ЧАСА) ============
def can_open_card(user_id):
    """Проверяет, может ли пользователь открыть карточку"""
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

def get_rarity_by_chance():
    rand = random.randint(1, 100)
    
    if rand <= RARITIES['mythical']['chance']:
        return 'mythical'
    elif rand <= RARITIES['mythical']['chance'] + RARITIES['legendary']['chance']:
        return 'legendary'
    elif rand <= RARITIES['mythical']['chance'] + RARITIES['legendary']['chance'] + RARITIES['epic']['chance']:
        return 'epic'
    elif rand <= RARITIES['mythical']['chance'] + RARITIES['legendary']['chance'] + RARITIES['epic']['chance'] + RARITIES['rare']['chance']:
        return 'rare'
    else:
        return 'common'

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

def get_user_collection(user_id):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT c.* FROM cards c
    JOIN user_cards uc ON c.card_id = uc.card_id
    WHERE uc.user_id = ?
    ORDER BY uc.opened_date DESC
    ''', (user_id,))
    cards = cursor.fetchall()
    conn.close()
    return cards

# ============ КЛАВИАТУРА ============
def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_random = types.KeyboardButton('🎴 Открыть карточку')
    btn_collection = types.KeyboardButton('📚 Моя коллекция')
    btn_stats = types.KeyboardButton('📊 Статистика')
    btn_rarities = types.KeyboardButton('💎 Редкости')
    keyboard.add(btn_random, btn_collection, btn_stats, btn_rarities)
    return keyboard

def admin_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_add_card = types.KeyboardButton('➕ Добавить карточку')
    btn_back = types.KeyboardButton('◀️ Назад в меню')
    keyboard.add(btn_add_card, btn_back)
    return keyboard

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

def send_card(message, card):
    card_id, name, team, country, rarity, image_path, added_by, added_date = card
    card_text = get_card_text(card)
    
    keyboard = types.InlineKeyboardMarkup()
    btn_collect = types.InlineKeyboardButton(text="📥 В коллекцию", callback_data=f"collect_{card_id}")
    btn_share = types.InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_{card_id}")
    keyboard.add(btn_collect, btn_share)
    
    if image_path and os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption=card_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
    else:
        bot.send_message(
            message.chat.id,
            card_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

# ============ КОМАНДЫ ДЛЯ ИГРОКОВ ============
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "user"
    
    register_user(user_id, username)
    cards_opened = get_user_stats(user_id)
    collection_count = get_user_collection_count(user_id)
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cards")
    total_cards = cursor.fetchone()[0]
    conn.close()
    
    is_admin = "👑 **Вы администратор!**" if user_id in ADMIN_IDS else ""
    
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

💡 Нажми **"🎴 Открыть карточку"** чтобы начать!"""
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_keyboard(), parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '🎴 Открыть карточку')
def open_card(message):
    user_id = message.from_user.id
    
    can_open, wait_time, cards_opened = can_open_card(user_id)
    
    if not can_open:
        bot.send_message(
            message.chat.id,
            f"⏰ **КД 2 ЧАСА!**\n\nСледующую карточку можно открыть через: **{wait_time}**\n\n📊 Всего открыто карточек: {cards_opened}",
            parse_mode='Markdown'
        )
        return
    
    card = get_random_card()
    
    if not card:
        bot.send_message(message.chat.id, "❌ В базе пока нет карточек! Обратитесь к администратору.")
        return
    
    update_card_time(user_id)
    save_user_card(user_id, card[0])
    send_card(message, card)
    
    next_time = datetime.now() + timedelta(hours=2)
    next_time_str = next_time.strftime('%H:%M:%S')
    bot.send_message(
        message.chat.id,
        f"⏰ Следующую карточку можно открыть через 2 часа (после {next_time_str})",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == '📚 Моя коллекция')
def show_collection(message):
    user_id = message.from_user.id
    cards = get_user_collection(user_id)
    
    if not cards:
        bot.send_message(
            message.chat.id,
            "📭 **Ваша коллекция пуста!**\n\nНажми **🎴 Открыть карточку** чтобы начать собирать!",
            parse_mode='Markdown'
        )
        return
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cards")
    total_cards = cursor.fetchone()[0]
    conn.close()
    
    rarity_counts = {'common': 0, 'rare': 0, 'epic': 0, 'mythical': 0, 'legendary': 0}
    for card in cards:
        rarity_counts[card[4]] += 1
    
    text = f"📚 **ВАША КОЛЛЕКЦИЯ**\n\n"
    text += f"📊 **Всего карточек:** {len(cards)} / {total_cards}\n"
    text += f"📈 **Прогресс:** {len(cards)/total_cards*100:.1f}%\n\n" if total_cards > 0 else ""
    text += f"💎 **По редкостям:**\n"
    text += f"⬜ Обычные: {rarity_counts['common']}\n"
    text += f"🔵 Редкие: {rarity_counts['rare']}\n"
    text += f"🟣 Эпические: {rarity_counts['epic']}\n"
    text += f"🔴 Мифические: {rarity_counts['mythical']}\n"
    text += f"🟡 Легендарные: {rarity_counts['legendary']}\n\n"
    text += f"📋 **Последние карточки:**\n"
    
    for card in cards[:10]:
        rarity_info = RARITIES[card[4]]
        text += f"{rarity_info['emoji']} {card[1]} ({card[2]}) — {rarity_info['name']}\n"
    
    if len(cards) > 10:
        text += f"\n... и еще {len(cards) - 10} карточек"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def show_stats(message):
    user_id = message.from_user.id
    cards_opened = get_user_stats(user_id)
    collection_count = get_user_collection_count(user_id)
    
    cards = get_user_collection(user_id)
    rarity_counts = {'common': 0, 'rare': 0, 'epic': 0, 'mythical': 0, 'legendary': 0}
    for card in cards:
        rarity_counts[card[4]] += 1
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cards")
    total_cards = cursor.fetchone()[0]
    conn.close()
    
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
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '💎 Редкости')
def show_rarities(message):
    text = f"💎 **РЕДКОСТИ КАРТОЧЕК**\n\n"
    
    for key, rarity in RARITIES.items():
        text += f"{rarity['emoji']} **{rarity['name']}**\n"
        text += f"   Шанс выпадения: {rarity['chance']}%\n"
        text += f"   {rarity['icon']} {rarity['icon']} {rarity['icon']}\n\n"
    
    text += f"✨ **Чем реже карточка, тем она ценнее!**\n"
    text += f"🔴 Мифические карточки выпадают с шансом 10%!\n"
    text += f"🟡 Легендарные карточки выпадают с шансом 5%!"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# ============ АДМИН-КОМАНДЫ ============
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    
    bot.send_message(
        message.chat.id,
        "🔧 **АДМИН-ПАНЕЛЬ**\n\n"
        "➕ **Добавить карточку** — нажми на кнопку\n"
        "📋 **Список карточек** — /cardslist\n"
        "🗑️ **Удалить карточку** — /delcard ID\n"
        "⏰ **Сбросить КД** — /resetcd @username\n"
        "⚡ **Сбросить свой КД** — /resetcd\n"
        "💾 **Бэкап** — /backup\n"
        "📊 **Статистика БД** — /dbstats\n"
        "👑 **Админы** — /admins",
        reply_markup=admin_keyboard(),
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['resetcd'])
def reset_cd(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) == 1:
            user_id = message.from_user.id
            conn = sqlite3.connect('hockey_cards.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET last_card_time = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, "✅ Ваш КД сброшен! Можете открыть новую карточку.")
            
        elif len(parts) == 2:
            user_input = parts[1].replace('@', '')
            conn = sqlite3.connect('hockey_cards.db')
            cursor = conn.cursor()
            
            if user_input.isdigit():
                cursor.execute("UPDATE users SET last_card_time = NULL WHERE user_id = ?", (int(user_input),))
            else:
                cursor.execute("UPDATE users SET last_card_time = NULL WHERE username = ?", (user_input,))
            
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                bot.send_message(message.chat.id, f"✅ КД сброшен для {user_input}")
            else:
                bot.send_message(message.chat.id, f"❌ Пользователь {user_input} не найден")
        else:
            bot.send_message(message.chat.id, "❌ Используйте:\n/resetcd — для себя\n/resetcd @username — для другого")
            
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['backup'])
def manual_backup(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    
    try:
        if not os.path.exists('backups'):
            os.makedirs('backups')
        
        backup_name = f"backups/hockey_cards_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2('hockey_cards.db', backup_name)
        
        # Отправляем бэкап в Telegram
        with open(backup_name, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"✅ Бэкап создан: {backup_name}")
        
        bot.send_message(message.chat.id, f"✅ Бэкап создан! Файл: {backup_name}")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['dbstats'])
def db_stats(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
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
    
    backups = []
    if os.path.exists('backups'):
        backups = sorted([f for f in os.listdir('backups') if f.startswith('hockey_cards_backup_')])[-5:]
    
    conn.close()
    
    text = f"📊 **СТАТИСТИКА БАЗЫ ДАННЫХ**\n\n"
    text += f"💾 **Размер БД:** {db_size:.1f} KB\n"
    text += f"🃏 **Всего карточек:** {total_cards}\n"
    text += f"👥 **Всего игроков:** {total_users}\n"
    text += f"📚 **Всего в коллекциях:** {total_collections}\n\n"
    
    if backups:
        text += f"📦 **Последние бэкапы:**\n"
        for backup in backups:
            backup_path = os.path.join('backups', backup)
            backup_size = os.path.getsize(backup_path) / 1024
            text += f"• {backup} ({backup_size:.1f} KB)\n"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['admins'])
def list_admins(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
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
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /addadmin @username или /addadmin ID")
            return
        
        user_input = parts[1].replace('@', '')
        
        conn = sqlite3.connect('hockey_cards.db')
        cursor = conn.cursor()
        
        if user_input.isdigit():
            cursor.execute("SELECT user_id, username FROM users WHERE user_id = ?", (int(user_input),))
        else:
            cursor.execute("SELECT user_id, username FROM users WHERE username = ?", (user_input,))
        
        user = cursor.fetchone()
        
        if not user:
            bot.send_message(message.chat.id, f"❌ Пользователь {user_input} не найден!")
            conn.close()
            return
        
        new_admin_id, username = user
        
        if new_admin_id in ADMIN_IDS:
            bot.send_message(message.chat.id, f"⚠️ @{username} уже является админом!")
            conn.close()
            return
        
        ADMIN_IDS.append(new_admin_id)
        cursor.execute("INSERT OR REPLACE INTO admins (user_id) VALUES (?)", (new_admin_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ @{username} теперь админ!")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['removeadmin'])
def remove_admin(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /removeadmin @username или /removeadmin ID")
            return
        
        user_input = parts[1].replace('@', '')
        
        conn = sqlite3.connect('hockey_cards.db')
        cursor = conn.cursor()
        
        if user_input.isdigit():
            cursor.execute("SELECT user_id, username FROM users WHERE user_id = ?", (int(user_input),))
        else:
            cursor.execute("SELECT user_id, username FROM users WHERE username = ?", (user_input,))
        
        user = cursor.fetchone()
        
        if not user:
            bot.send_message(message.chat.id, f"❌ Пользователь {user_input} не найден!")
            conn.close()
            return
        
        admin_id, username = user
        
        if admin_id == message.from_user.id:
            bot.send_message(message.chat.id, "❌ Вы не можете удалить самого себя!")
            conn.close()
            return
        
        if admin_id not in ADMIN_IDS:
            bot.send_message(message.chat.id, f"⚠️ @{username} не является админом!")
            conn.close()
            return
        
        ADMIN_IDS.remove(admin_id)
        cursor.execute("DELETE FROM admins WHERE user_id = ?", (admin_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ @{username} больше не админ!")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == '➕ Добавить карточку')
def start_add_card(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    
    temp_card_data[message.from_user.id] = {}
    msg = bot.send_message(message.chat.id, "📝 Введите **имя игрока**:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_card_name)

def process_card_name(message):
    user_id = message.from_user.id
    if user_id not in temp_card_data:
        temp_card_data[user_id] = {}
    
    temp_card_data[user_id]['name'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "🏆 Введите **команду**:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_card_team)

def process_card_team(message):
    user_id = message.from_user.id
    temp_card_data[user_id]['team'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "🌍 Введите **страну**:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_card_country)

def process_card_country(message):
    user_id = message.from_user.id
    temp_card_data[user_id]['country'] = message.text.strip()
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for key, rarity in RARITIES.items():
        btn = types.InlineKeyboardButton(
            text=f"{rarity['emoji']} {rarity['name']}",
            callback_data=f"set_rarity_{key}"
        )
        keyboard.add(btn)
    
    bot.send_message(
        message.chat.id,
        "💎 Выберите **редкость** карточки:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_rarity_'))
def process_card_rarity(call):
    user_id = call.from_user.id
    rarity = call.data.split('_')[2]
    
    if user_id not in temp_card_data:
        temp_card_data[user_id] = {}
    
    temp_card_data[user_id]['rarity'] = rarity
    
    bot.edit_message_text(
        f"✅ Редкость выбрана: {RARITIES[rarity]['emoji']} {RARITIES[rarity]['name']}\n\n📸 Теперь отправьте **изображение** карточки (фото или картинку) или нажмите любую кнопку чтобы пропустить:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )
    
    msg = bot.send_message(call.message.chat.id, "🖼️ Отправьте фото игрока (или нажмите любую кнопку чтобы пропустить):")
    bot.register_next_step_handler(msg, process_card_image)

def process_card_image(message):
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
    
    bot.send_message(
        message.chat.id,
        f"✅ **Карточка успешно добавлена!**\n\n{card_text}\n🆔 ID: {card_id}",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['cardslist'])
def list_cards(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT card_id, name, team, rarity FROM cards ORDER BY card_id")
    cards = cursor.fetchall()
    conn.close()
    
    if not cards:
        bot.send_message(message.chat.id, "📭 В базе нет карточек.")
        return
    
    text = "📋 **СПИСОК КАРТОЧЕК**\n\n"
    for card in cards:
        rarity_info = RARITIES[card[3]]
        text += f"{rarity_info['emoji']} **ID:{card[0]}** {card[1]} ({card[2]}) — {rarity_info['name']}\n"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['delcard'])
def delete_card(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /delcard ID_карточки")
            return
        
        card_id = int(parts[1])
        
        conn = sqlite3.connect('hockey_cards.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name, image_path FROM cards WHERE card_id = ?", (card_id,))
        card = cursor.fetchone()
        
        if not card:
            bot.send_message(message.chat.id, f"❌ Карточка с ID {card_id} не найдена!")
            conn.close()
            return
        
        if card[1] and os.path.exists(card[1]):
            os.remove(card[1])
        
        cursor.execute("DELETE FROM cards WHERE card_id = ?", (card_id,))
        cursor.execute("DELETE FROM user_cards WHERE card_id = ?", (card_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Карточка **{card[0]}** удалена!", parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == '◀️ Назад в меню')
def back_to_menu(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    
    bot.send_message(message.chat.id, "🏒 Главное меню:", reply_markup=main_keyboard())

# ============ INLINE CALLBACKS ============
@bot.callback_query_handler(func=lambda call: call.data.startswith('collect_'))
def collect_card(call):
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
    
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('share_'))
def share_card(call):
    card_id = int(call.data.split('_')[1])
    card = get_card_by_id(card_id)
    
    if card:
        rarity_info = RARITIES[card[4]]
        share_text = f"🏒 Хоккейная карточка\n\n{rarity_info['icon']} {card[1]} ({card[2]}) — {rarity_info['name']}\n🌍 {card[3]}\n🆔 #{card_id}\n\nПолучи свою карточку!"
        bot.answer_callback_query(call.id, "Карточка скопирована!", show_alert=True)
        bot.send_message(call.message.chat.id, share_text, parse_mode='Markdown')

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
# =================================================

# ============ ЗАПУСК ============
if __name__ == '__main__':
    init_db()
    update_db_users()
    print("🤖 Бот хоккейных карточек запущен на Render!")
    print("💎 Редкости: Обычная (45%), Редкая (25%), Эпическая (15%), Мифическая (10%), Легендарная (5%)")
    print("⏰ КД на открытие: 2 ЧАСА")
    print(f"👑 Количество админов: {len(ADMIN_IDS)}")
    print("📸 Можно добавлять карточки с изображениями!")
    print("💾 Автосохранение: каждые 5 минут")
    print("📦 Авто-бэкап: каждые 24 часа")
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")
            time.sleep(10)
