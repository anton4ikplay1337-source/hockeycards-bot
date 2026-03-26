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

# ============ НАСТРОЙКИ ============
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
admin_ids_str = os.environ.get('ADMIN_IDS', '123456789')
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(',')]

if 'ADMIN_ID' in os.environ:
    old_admin = int(os.environ.get('ADMIN_ID'))
    if old_admin not in ADMIN_IDS:
        ADMIN_IDS.append(old_admin)

bot = telebot.TeleBot(TOKEN)

# Словари для временных данных
temp_card_data = {}
last_open_time = {}
active_matches = {}
temp_promo_data = {}
user_collection_page = {}
match_requests = {}

# ============ ПОЗИЦИИ ИГРОКОВ ============
POSITIONS = {
    'goalkeeper': {'name': 'Вратарь', 'emoji': '🥅', 'defense_bonus': 20, 'icon': '🧤', 'color': '🔵'},
    'defender': {'name': 'Защитник', 'emoji': '🛡️', 'tackle_bonus': 10, 'icon': '⚔️', 'color': '🟢'},
    'forward': {'name': 'Нападающий', 'emoji': '🏒', 'shot_bonus': 15, 'icon': '⚡', 'color': '🔴'}
}

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
        position TEXT,
        rarity TEXT,
        image_path TEXT,
        added_by INTEGER,
        added_date TEXT
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 1000,
        position TEXT DEFAULT 'forward',
        squad TEXT DEFAULT '[]',
        last_card_time TEXT DEFAULT NULL,
        cards_opened INTEGER DEFAULT 0,
        total_cards INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_cards (
        user_id INTEGER,
        card_id INTEGER,
        opened_date TEXT,
        PRIMARY KEY (user_id, card_id)
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS promo_codes (
        code TEXT PRIMARY KEY,
        reward INTEGER,
        is_active INTEGER DEFAULT 1,
        expiry_date TEXT,
        uses_limit INTEGER DEFAULT 1,
        uses_count INTEGER DEFAULT 0
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS matches_history (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        player1_id INTEGER,
        player2_id INTEGER,
        player1_score INTEGER,
        player2_score INTEGER,
        winner_id INTEGER,
        match_date TEXT
    )''')
    
    conn.commit()
    conn.close()

def update_db_users():
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN position TEXT DEFAULT 'forward'")
    except: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN squad TEXT DEFAULT '[]'")
    except: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_card_time TEXT DEFAULT NULL")
    except: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN cards_opened INTEGER DEFAULT 0")
    except: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN total_cards INTEGER DEFAULT 0")
    except: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN wins INTEGER DEFAULT 0")
    except: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN losses INTEGER DEFAULT 0")
    except: pass
    try:
        cursor.execute("SELECT user_id FROM admins")
        db_admins = cursor.fetchall()
        for admin in db_admins:
            if admin[0] not in ADMIN_IDS:
                ADMIN_IDS.append(admin[0])
    except: pass
    conn.commit()
    conn.close()

def register_user(user_id, username):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def get_user_position(user_id):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT position FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'forward'

def set_user_position(user_id, position):
    if position not in POSITIONS:
        return False
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET position = ? WHERE user_id = ?", (position, user_id))
    conn.commit()
    conn.close()
    return True

def get_user_squad(user_id):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT squad FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return json.loads(result[0]) if result and result[0] else []

def add_to_squad(user_id, card_id):
    squad = get_user_squad(user_id)
    if card_id in squad:
        return False
    squad.append(card_id)
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET squad = ? WHERE user_id = ?", (json.dumps(squad), user_id))
    conn.commit()
    conn.close()
    return True

def remove_from_squad(user_id, card_id):
    squad = get_user_squad(user_id)
    if card_id not in squad:
        return False
    squad.remove(card_id)
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET squad = ? WHERE user_id = ?", (json.dumps(squad), user_id))
    conn.commit()
    conn.close()
    return True

# ============ ФУНКЦИИ ДЛЯ КАРТОЧЕК ============
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
    cursor.execute("SELECT cards_opened, wins, losses, balance FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result if result else (0, 0, 0, 0)

def get_balance(user_id):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_balance(user_id, amount):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_card_to_db(name, team, country, position, rarity, image_path, added_by):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO cards (name, team, country, position, rarity, image_path, added_by, added_date)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
    (name, team, country, position, rarity, image_path, added_by, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
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
    LIMIT ? OFFSET ?''', (user_id, limit, offset))
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

# ============ ФУНКЦИИ ДЛЯ ПРОМОКОДОВ ============
def generate_promo_code():
    return ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789', k=8))

def create_promo_code(code, reward, days=7, uses_limit=1):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    cursor.execute("INSERT INTO promo_codes (code, reward, expiry_date, uses_limit) VALUES (?, ?, ?, ?)",
                  (code, reward, expiry, uses_limit))
    conn.commit()
    conn.close()
    return code

def activate_promo_code(user_id, code):
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT reward, is_active, expiry_date, uses_limit, uses_count FROM promo_codes WHERE code = ?", (code,))
    promo = cursor.fetchone()
    if not promo:
        conn.close()
        return False, "❌ Промокод не найден!"
    reward, is_active, expiry_date, uses_limit, uses_count = promo
    if not is_active:
        conn.close()
        return False, "❌ Промокод неактивен!"
    if datetime.now() > datetime.strptime(expiry_date, '%Y-%m-%d'):
        conn.close()
        return False, "❌ Срок действия промокода истек!"
    if uses_count >= uses_limit:
        conn.close()
        return False, "❌ Промокод уже использован!"
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, user_id))
    cursor.execute("UPDATE promo_codes SET uses_count = uses_count + 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    return True, f"✅ Промокод активирован! Вы получили {reward} ₽!"

# ============ ФУНКЦИИ ДЛЯ МАТЧЕЙ ============
def create_match_request(from_user_id, to_user_id):
    match_requests[from_user_id] = to_user_id
    return True

def get_match_request(user_id):
    for requester, target in match_requests.items():
        if target == user_id:
            return requester
    return None

def remove_match_request(user_id):
    if user_id in match_requests:
        del match_requests[user_id]
    for requester, target in list(match_requests.items()):
        if target == user_id:
            del match_requests[requester]

def start_match(player1_id, player2_id):
    match_id = random.randint(100000, 999999)
    active_matches[match_id] = {
        'player1': player1_id,
        'player2': player2_id,
        'period': 1,
        'time': 0,
        'score1': 0,
        'score2': 0,
        'current_turn': player1_id,
        'events': [],
        'position1': get_user_position(player1_id),
        'position2': get_user_position(player2_id),
        'squad1': get_user_squad(player1_id),
        'squad2': get_user_squad(player2_id)
    }
    return match_id

def get_username(user_id):
    try:
        user = bot.get_chat(user_id)
        return user.username or str(user_id)
    except:
        return str(user_id)

def simulate_shot(position, squad):
    """Симулирует бросок с учетом позиции и состава"""
    base_chance = 0.30
    if position == 'forward':
        base_chance += 0.15
    elif position == 'goalkeeper':
        base_chance -= 0.10
    # Бонус от состава (каждый игрок в составе дает +1%)
    base_chance += len(squad) * 0.01
    return random.random() < base_chance

def simulate_tackle(position, squad):
    """Симулирует отбор с учетом позиции и состава"""
    base_chance = 0.50
    if position == 'defender':
        base_chance += 0.10
    elif position == 'goalkeeper':
        base_chance -= 0.15
    # Бонус от состава
    base_chance += len(squad) * 0.01
    return random.random() < base_chance

def process_match_action(match_id, player_id, action):
    if match_id not in active_matches:
        return None, "Матч не найден!"
    
    game = active_matches[match_id]
    
    if game['current_turn'] != player_id:
        return None, "Сейчас не ваш ход!"
    
    position = get_user_position(player_id)
    squad = get_user_squad(player_id)
    pos_info = POSITIONS[position]
    
    if action == 'shot':
        success = simulate_shot(position, squad)
        if success:
            if player_id == game['player1']:
                game['score1'] += 1
                event = f"🏒 ГОЛ! @{get_username(player_id)} забивает! {game['score1']}:{game['score2']}"
            else:
                game['score2'] += 1
                event = f"🏒 ГОЛ! @{get_username(player_id)} забивает! {game['score1']}:{game['score2']}"
        else:
            event = f"🧤 {pos_info['icon']} {pos_info['name']} @{get_username(player_id)} не смог забить!"
        
        game['events'].append(event)
        game['time'] += 1
        
    elif action == 'pass':
        game['events'].append(f"🔄 {pos_info['icon']} {pos_info['name']} @{get_username(player_id)} делает пас!")
        game['time'] += 1
        
    elif action == 'tackle':
        success = simulate_tackle(position, squad)
        if success:
            game['events'].append(f"⚡ {pos_info['icon']} {pos_info['name']} @{get_username(player_id)} отбирает шайбу!")
        else:
            game['events'].append(f"❌ {pos_info['icon']} {pos_info['name']} @{get_username(player_id)} не смог отобрать шайбу!")
        game['time'] += 1
    
    # Смена хода
    game['current_turn'] = game['player2'] if player_id == game['player1'] else game['player1']
    
    # Проверка окончания периода
    if game['time'] >= 20:
        game['period'] += 1
        game['time'] = 0
        game['events'].append(f"🔔 КОНЕЦ {game['period']-1}-го ПЕРИОДА! Счет {game['score1']}:{game['score2']}")
        
        if game['period'] > 3:
            # Матч окончен
            winner = game['player1'] if game['score1'] > game['score2'] else game['player2']
            if game['score1'] == game['score2']:
                winner = game['player1'] if random.random() < 0.5 else game['player2']
                if winner == game['player1']:
                    game['score1'] += 1
                else:
                    game['score2'] += 1
                game['events'].append(f"🚨 ОВЕРТАЙМ! Победа в дополнительное время! {game['score1']}:{game['score2']}")
            
            # Сохраняем результат
            conn = sqlite3.connect('hockey_cards.db')
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO matches_history (player1_id, player2_id, player1_score, player2_score, winner_id, match_date)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (game['player1'], game['player2'], game['score1'], game['score2'], winner, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            conn.close()
            
            # Обновляем статистику
            update_balance(winner, 50)
            conn = sqlite3.connect('hockey_cards.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (winner,))
            loser = game['player2'] if winner == game['player1'] else game['player1']
            cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (loser,))
            conn.commit()
            conn.close()
            
            winner_name = get_username(winner)
            result_msg = f"🏆 **МАТЧ ОКОНЧЕН!**\n\nИтоговый счет: {game['score1']}:{game['score2']}\n\nПобедитель: @{winner_name}\n\n💰 Победитель получает 50 монет!"
            
            final_result = {
                'result': result_msg,
                'events': game['events'][-10:],
                'score1': game['score1'],
                'score2': game['score2']
            }
            del active_matches[match_id]
            return final_result, None
        
        return None, f"ПЕРИОД {game['period']} начался! Счет {game['score1']}:{game['score2']}"
    
    return game, None

# ============ КАРТОЧКА ============
def get_card_text(card):
    card_id, name, team, country, position, rarity, image_path, added_by, added_date = card
    rarity_info = RARITIES[rarity]
    pos_info = POSITIONS.get(position, POSITIONS['forward'])
    
    text = f"""{rarity_info['icon']} **{rarity_info['name']} КАРТОЧКА** {rarity_info['icon']}

🏒 **{name}**

🏆 **Команда:** {team}
🌍 **Страна:** {country}
🎭 **Позиция:** {pos_info['emoji']} {pos_info['name']}
💎 **Редкость:** {rarity_info['emoji']} {rarity_info['name']}
🆔 **ID:** #{card_id}

✨ Удачи в коллекционировании!"""
    return text

def get_card_keyboard(card_id, user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_cards WHERE user_id = ? AND card_id = ?", (user_id, card_id))
    has_card = cursor.fetchone() is not None
    conn.close()
    
    squad = get_user_squad(user_id)
    in_squad = card_id in squad
    
    if has_card:
        if in_squad:
            btn_squad = types.InlineKeyboardButton(text="❌ Убрать из состава", callback_data=f"remove_squad_{card_id}")
        else:
            btn_squad = types.InlineKeyboardButton(text="➕ В состав", callback_data=f"add_squad_{card_id}")
        btn_collect = types.InlineKeyboardButton(text="✅ В коллекции", callback_data="already_collected")
    else:
        btn_collect = types.InlineKeyboardButton(text="📥 В коллекцию", callback_data=f"collect_{card_id}")
        btn_squad = types.InlineKeyboardButton(text="🚫 Нет в коллекции", callback_data="no_card")
    
    btn_share = types.InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_{card_id}")
    btn_back = types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    
    if has_card:
        keyboard.add(btn_collect, btn_squad, btn_share, btn_back)
    else:
        keyboard.add(btn_collect, btn_share, btn_back)
    return keyboard

def back_to_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main"))
    return keyboard

# ============ ОСНОВНОЕ МЕНЮ ============
def main_menu_keyboard(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_open = types.InlineKeyboardButton(text="🎴 Открыть карточку", callback_data="open_card")
    btn_collection = types.InlineKeyboardButton(text="📚 Моя коллекция", callback_data="show_collection_0")
    btn_stats = types.InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")
    btn_rarities = types.InlineKeyboardButton(text="💎 Редкости", callback_data="show_rarities")
    btn_match = types.InlineKeyboardButton(text="🏒 Сыграть матч", callback_data="match_menu")
    btn_balance = types.InlineKeyboardButton(text="💰 Баланс", callback_data="show_balance")
    btn_profile = types.InlineKeyboardButton(text="👤 Мой профиль", callback_data="show_profile")
    btn_squad = types.InlineKeyboardButton(text="⭐ Мой состав", callback_data="show_squad")
    
    keyboard.add(btn_open, btn_collection, btn_stats, btn_rarities, btn_match, btn_balance, btn_profile, btn_squad)
    
    if user_id in ADMIN_IDS:
        btn_admin = types.InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin_panel")
        keyboard.add(btn_admin)
    
    return keyboard

# ============ ПРОФИЛЬ ============
@bot.callback_query_handler(func=lambda call: call.data == "show_profile")
def show_profile(call):
    user_id = call.from_user.id
    username = call.from_user.username or "user"
    
    cards_opened, wins, losses, balance = get_user_stats(user_id)
    position = get_user_position(user_id)
    pos_info = POSITIONS[position]
    collection_count = get_user_collection_count(user_id)
    total_cards = get_total_cards_count()
    squad = get_user_squad(user_id)
    
    # Вычисляем процент побед отдельно, чтобы избежать ошибки в f-string
    if wins + losses > 0:
        win_percent = wins / (wins + losses) * 100
        win_text = f"{win_percent:.1f}%"
    else:
        win_text = "0%"
    
    text = f"""👤 **ПРОФИЛЬ ИГРОКА**

📱 **Telegram:** @{username}
🆔 **ID:** `{user_id}`

🎭 **Позиция:** {pos_info['emoji']} {pos_info['name']}
💰 **Баланс:** {balance} ₽

📊 **СТАТИСТИКА:**
• 🎴 Карточек открыто: {cards_opened}
• 📚 В коллекции: {collection_count} / {total_cards}
• 🏆 Побед: {wins}
• ❌ Поражений: {losses}
• 📈 Процент побед: {win_text}

⭐ **СОСТАВ:**
• Игроков в составе: {len(squad)}/10
• Бонус к игре: +{len(squad)}% к шансам

💡 Чтобы изменить позицию, используй кнопку ниже!"""
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_change_pos = types.InlineKeyboardButton(text="🔄 Сменить позицию", callback_data="change_position")
    btn_back = types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    keyboard.add(btn_change_pos, btn_back)
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "change_position")
def change_position_menu(call):
    user_id = call.from_user.id
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for pos_key, pos_info in POSITIONS.items():
        btn = types.InlineKeyboardButton(
            text=f"{pos_info['emoji']} {pos_info['name']} {pos_info['icon']}",
            callback_data=f"set_position_{pos_key}"
        )
        keyboard.add(btn)
    
    btn_back = types.InlineKeyboardButton(text="◀️ Назад", callback_data="show_profile")
    keyboard.add(btn_back)
    
    bot.edit_message_text("🎭 **Выберите новую позицию:**\n\n"
                         "🥅 **Вратарь** — +20% к защите\n"
                         "🛡️ **Защитник** — +10% к отбору\n"
                         "🏒 **Нападающий** — +15% к голу",
                         call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_position_'))
def set_position(call):
    user_id = call.from_user.id
    position = call.data.split('_')[2]
    
    if set_user_position(user_id, position):
        pos_info = POSITIONS[position]
        bot.answer_callback_query(call.id, f"✅ Позиция изменена на {pos_info['name']}!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка при смене позиции!", show_alert=True)
    
    show_profile(call)

# ============ СОСТАВ ============
@bot.callback_query_handler(func=lambda call: call.data == "show_squad")
def show_squad(call):
    user_id = call.from_user.id
    squad = get_user_squad(user_id)
    
    if not squad:
        text = "⭐ **ВАШ СОСТАВ**\n\nВ вашем составе пока нет игроков!\n\n💡 Добавляйте карточки в состав из коллекции, нажав на карточку и выбрав '➕ В состав'"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')
        return
    
    text = f"⭐ **ВАШ СОСТАВ** (Бонус: +{len(squad)}% к шансам)\n\n"
    
    for i, card_id in enumerate(squad[:10], 1):
        card = get_card_by_id(card_id)
        if card:
            rarity_info = RARITIES[card[4]]
            pos_info = POSITIONS.get(card[3], POSITIONS['forward'])
            text += f"{i}. {pos_info['emoji']} **{card[1]}** ({card[2]}) — {rarity_info['emoji']} {rarity_info['name']}\n"
    
    if len(squad) > 10:
        text += f"\n... и еще {len(squad)-10} игроков в резерве"
    
    keyboard = types.InlineKeyboardMarkup()
    btn_clear = types.InlineKeyboardButton(text="🗑️ Очистить состав", callback_data="clear_squad")
    btn_back = types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    keyboard.add(btn_clear, btn_back)
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "clear_squad")
def clear_squad(call):
    user_id = call.from_user.id
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET squad = '[]' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, "✅ Состав очищен!", show_alert=True)
    show_squad(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith('add_squad_'))
def add_to_squad_callback(call):
    user_id = call.from_user.id
    card_id = int(call.data.split('_')[2])
    
    squad = get_user_squad(user_id)
    if len(squad) >= 10:
        bot.answer_callback_query(call.id, "⚠️ В составе может быть не более 10 игроков!", show_alert=True)
        return
    
    if add_to_squad(user_id, card_id):
        bot.answer_callback_query(call.id, "✅ Игрок добавлен в состав!", show_alert=True)
        card = get_card_by_id(card_id)
        if card:
            card_text = get_card_text(card)
            keyboard = get_card_keyboard(card_id, user_id)
            bot.edit_message_text(card_text, call.message.chat.id, call.message.message_id,
                                 reply_markup=keyboard, parse_mode='Markdown')
    else:
        bot.answer_callback_query(call.id, "⚠️ Игрок уже в составе!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_squad_'))
def remove_from_squad_callback(call):
    user_id = call.from_user.id
    card_id = int(call.data.split('_')[2])
    
    if remove_from_squad(user_id, card_id):
        bot.answer_callback_query(call.id, "✅ Игрок удален из состава!", show_alert=True)
        card = get_card_by_id(card_id)
        if card:
            card_text = get_card_text(card)
            keyboard = get_card_keyboard(card_id, user_id)
            bot.edit_message_text(card_text, call.message.chat.id, call.message.message_id,
                                 reply_markup=keyboard, parse_mode='Markdown')
    else:
        bot.answer_callback_query(call.id, "⚠️ Игрок не был в составе!", show_alert=True)

# ============ ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ============
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "user"
    
    register_user(user_id, username)
    cards_opened, wins, losses, balance = get_user_stats(user_id)
    collection_count = get_user_collection_count(user_id)
    total_cards = get_total_cards_count()
    position = get_user_position(user_id)
    pos_info = POSITIONS[position]
    
    is_admin = "👑 **Вы администратор!**" if user_id in ADMIN_IDS else ""
    
    welcome_text = f"""🏒 **КАРТОЧКИ МХЛ | ХОККЕЙНЫЕ МАТЧИ** {is_admin}

📇 **Добро пожаловать!**

🎴 **Что ты можешь делать:**
• Открывать новые карточки (КД 2 часа)
• Собирать коллекцию и составлять команду
• Играть в хоккейные матчи 1 на 1
• Активировать промокоды

📊 **Твоя статистика:**
• 🎴 Открыто карточек: {cards_opened}
• 📚 В коллекции: {collection_count} / {total_cards}
• 🏆 Побед: {wins} | Поражений: {losses}
• 💰 Баланс: {balance} ₽
• 🎭 Позиция: {pos_info['emoji']} {pos_info['name']}

💡 Нажми на кнопки ниже!"""
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard(user_id), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main(call):
    user_id = call.from_user.id
    cards_opened, wins, losses, balance = get_user_stats(user_id)
    collection_count = get_user_collection_count(user_id)
    total_cards = get_total_cards_count()
    position = get_user_position(user_id)
    pos_info = POSITIONS[position]
    
    is_admin = "👑 **Вы администратор!**" if user_id in ADMIN_IDS else ""
    
    text = f"""🏒 **КАРТОЧКИ МХЛ | ХОККЕЙНЫЕ МАТЧИ** {is_admin}

📇 **Главное меню**

📊 **Твоя статистика:**
• 🎴 Открыто карточек: {cards_opened}
• 📚 В коллекции: {collection_count} / {total_cards}
• 🏆 Побед: {wins} | Поражений: {losses}
• 💰 Баланс: {balance} ₽
• 🎭 Позиция: {pos_info['emoji']} {pos_info['name']}

💡 Выбери действие:"""
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, 
                          reply_markup=main_menu_keyboard(user_id), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "show_balance")
def show_balance(call):
    user_id = call.from_user.id
    balance = get_balance(user_id)
    bot.edit_message_text(f"💰 **Ваш баланс:** {balance} ₽", 
                         call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "open_card")
def open_card_callback(call):
    user_id = call.from_user.id
    now_time = time.time()
    
    if user_id in last_open_time:
        if now_time - last_open_time[user_id] < 5:
            bot.answer_callback_query(call.id, "⏳ Подожди 5 секунд!", show_alert=True)
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

@bot.callback_query_handler(func=lambda call: call.data.startswith('show_collection_'))
def show_collection_callback(call):
    user_id = call.from_user.id
    page = int(call.data.split('_')[2]) if len(call.data.split('_')) > 2 else 0
    items_per_page = 10
    
    total_cards = get_user_collection_count(user_id)
    total_pages = (total_cards + items_per_page - 1) // items_per_page
    
    if total_cards == 0:
        bot.edit_message_text("📭 **Ваша коллекция пуста!**", 
                             call.message.chat.id, call.message.message_id,
                             reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')
        return
    
    cards = get_user_collection(user_id, page * items_per_page, items_per_page)
    
    text = f"📚 **ВАША КОЛЛЕКЦИЯ** (стр. {page + 1}/{total_pages})\n\n"
    
    for card in cards:
        rarity_info = RARITIES[card[4]]
        pos_info = POSITIONS.get(card[3], POSITIONS['forward'])
        text += f"{rarity_info['emoji']} {pos_info['emoji']} **{card[1]}** ({card[2]}) — {rarity_info['name']}\n\n"
    
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    if page > 0:
        keyboard.add(types.InlineKeyboardButton(text="◀️ Предыдущая", callback_data=f"show_collection_{page-1}"))
    keyboard.add(types.InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main"))
    if page < total_pages - 1:
        keyboard.add(types.InlineKeyboardButton(text="Следующая ▶️", callback_data=f"show_collection_{page+1}"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "show_stats")
def show_stats_callback(call):
    user_id = call.from_user.id
    cards_opened, wins, losses, balance = get_user_stats(user_id)
    collection_count = get_user_collection_count(user_id)
    total_cards = get_total_cards_count()
    
    cards = get_user_collection(user_id, 0, 1000)
    rarity_counts = {'common': 0, 'rare': 0, 'epic': 0, 'mythical': 0, 'legendary': 0}
    position_counts = {'goalkeeper': 0, 'defender': 0, 'forward': 0}
    for card in cards:
        rarity_counts[card[4]] += 1
        if card[3] in position_counts:
            position_counts[card[3]] += 1
    
    collection_percent = (collection_count / total_cards * 100) if total_cards > 0 else 0
    win_percent = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    
    text = f"📊 **ВАША СТАТИСТИКА**\n\n"
    text += f"🎴 **Открыто карточек:** {cards_opened}\n"
    text += f"📚 **В коллекции:** {collection_count} / {total_cards}\n"
    text += f"📈 **Прогресс:** {collection_percent:.1f}%\n"
    text += f"🏆 **Матчи:** {wins} побед / {losses} поражений\n"
    text += f"📊 **Процент побед:** {win_percent:.1f}%\n"
    text += f"💰 **Баланс:** {balance} ₽\n\n"
    text += f"💎 **По редкостям:**\n"
    text += f"⬜ Обычные: {rarity_counts['common']}\n"
    text += f"🔵 Редкие: {rarity_counts['rare']}\n"
    text += f"🟣 Эпические: {rarity_counts['epic']}\n"
    text += f"🔴 Мифические: {rarity_counts['mythical']}\n"
    text += f"🟡 Легендарные: {rarity_counts['legendary']}\n\n"
    text += f"🎭 **По позициям:**\n"
    text += f"🥅 Вратари: {position_counts['goalkeeper']}\n"
    text += f"🛡️ Защитники: {position_counts['defender']}\n"
    text += f"🏒 Нападающие: {position_counts['forward']}\n\n"
    text += f"⏰ **КД на открытие:** 2 часа"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "show_rarities")
def show_rarities_callback(call):
    text = f"💎 **РЕДКОСТИ КАРТОЧЕК**\n\n"
    
    for key, rarity in RARITIES.items():
        text += f"{rarity['emoji']} **{rarity['name']}**\n"
        text += f"   Шанс выпадения: {rarity['chance']}%\n\n"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

# ============ МАТЧИ ============
@bot.callback_query_handler(func=lambda call: call.data == "match_menu")
def match_menu(call):
    user_id = call.from_user.id
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_find = types.InlineKeyboardButton(text="🔍 Найти соперника", callback_data="find_opponent")
    btn_history = types.InlineKeyboardButton(text="📜 История матчей", callback_data="match_history")
    btn_cancel = types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    keyboard.add(btn_find, btn_history, btn_cancel)
    
    bot.edit_message_text("🏒 **ХОККЕЙНЫЙ МАТЧ 1 НА 1**\n\nВыбери действие:", 
                         call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "find_opponent")
def find_opponent(call):
    user_id = call.from_user.id
    
    existing_request = get_match_request(user_id)
    if existing_request:
        bot.answer_callback_query(call.id, "У вас уже есть активный запрос на матч!", show_alert=True)
        return
    
    bot.edit_message_text("🔍 **Поиск соперника**\n\nВведите @username игрока, которому хотите бросить вызов:", 
                         call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    bot.register_next_step_handler(call.message, process_opponent_search, call.message.chat.id, call.message.message_id)

def process_opponent_search(message, chat_id, msg_id):
    user_id = message.from_user.id
    opponent_input = message.text.strip().replace('@', '')
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username FROM users WHERE username = ? OR user_id = ?", 
                  (opponent_input, opponent_input if opponent_input.isdigit() else 0))
    opponent = cursor.fetchone()
    conn.close()
    
    if not opponent:
        bot.send_message(message.chat.id, f"❌ Игрок @{opponent_input} не найден!")
        bot.send_message(chat_id, "🏒 Вернуться в меню:", reply_markup=main_menu_keyboard(user_id))
        return
    
    opponent_id, opponent_name = opponent
    
    if opponent_id == user_id:
        bot.send_message(message.chat.id, "❌ Нельзя играть с самим собой!")
        bot.send_message(chat_id, "🏒 Вернуться в меню:", reply_markup=main_menu_keyboard(user_id))
        return
    
    create_match_request(user_id, opponent_id)
    
    keyboard = types.InlineKeyboardMarkup()
    btn_accept = types.InlineKeyboardButton(text="✅ Принять вызов", callback_data=f"accept_match_{user_id}")
    btn_decline = types.InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_match_{user_id}")
    keyboard.add(btn_accept, btn_decline)
    
    try:
        bot.send_message(opponent_id, 
                        f"🏒 **ВЫЗОВ НА МАТЧ!**\n\nИгрок @{message.from_user.username} вызывает вас на хоккейный матч!\n\nПринять вызов?",
                        reply_markup=keyboard, parse_mode='Markdown')
        bot.send_message(message.chat.id, f"✅ Вызов отправлен игроку @{opponent_name}! Ожидайте ответа.")
        bot.send_message(chat_id, "🏒 Вернуться в меню:", reply_markup=main_menu_keyboard(user_id))
    except:
        bot.send_message(message.chat.id, f"❌ Не удалось отправить вызов игроку @{opponent_name}. Возможно, он не начал общение с ботом.")
        remove_match_request(user_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('accept_match_'))
def accept_match(call):
    challenger_id = int(call.data.split('_')[2])
    user_id = call.from_user.id
    
    if get_match_request(challenger_id) != user_id:
        bot.answer_callback_query(call.id, "❌ Запрос на матч не найден или уже отменен!", show_alert=True)
        return
    
    remove_match_request(challenger_id)
    match_id = start_match(challenger_id, user_id)
    
    challenger_name = get_username(challenger_id)
    user_name = get_username(user_id)
    
    game_keyboard = types.InlineKeyboardMarkup(row_width=3)
    btn_shot = types.InlineKeyboardButton(text="🏒 БРОСОК", callback_data=f"match_action_{match_id}_shot")
    btn_pass = types.InlineKeyboardButton(text="🔄 ПАС", callback_data=f"match_action_{match_id}_pass")
    btn_tackle = types.InlineKeyboardButton(text="⚡ ОТБОР", callback_data=f"match_action_{match_id}_tackle")
    game_keyboard.add(btn_shot, btn_pass, btn_tackle)
    
    match_text = f"🏒 **МАТЧ НАЧАЛСЯ!**\n\n{challenger_name} vs {user_name}\n\nПервый период!\nСчет: 0:0\n\nХод игрока: @{challenger_name}"
    
    bot.send_message(challenger_id, match_text, reply_markup=game_keyboard, parse_mode='Markdown')
    bot.send_message(user_id, match_text, reply_markup=game_keyboard, parse_mode='Markdown')
    
    bot.answer_callback_query(call.id, "✅ Матч начался!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('decline_match_'))
def decline_match(call):
    challenger_id = int(call.data.split('_')[2])
    user_id = call.from_user.id
    
    if get_match_request(challenger_id) == user_id:
        remove_match_request(challenger_id)
        bot.send_message(challenger_id, f"❌ Игрок @{get_username(user_id)} отклонил ваш вызов!")
        bot.answer_callback_query(call.id, "✅ Вы отклонили вызов!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "❌ Запрос не найден!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('match_action_'))
def match_action(call):
    user_id = call.from_user.id
    parts = call.data.split('_')
    match_id = int(parts[2])
    action = parts[3]
    
    if match_id not in active_matches:
        bot.answer_callback_query(call.id, "❌ Матч уже завершен!", show_alert=True)
        return
    
    game = active_matches[match_id]
    
    result, msg = process_match_action(match_id, user_id, action)
    
    if isinstance(result, dict) and 'result' in result:
        game_keyboard = types.InlineKeyboardMarkup()
        btn_menu = types.InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")
        game_keyboard.add(btn_menu)
        
        bot.send_message(game['player1'], result['result'], reply_markup=game_keyboard, parse_mode='Markdown')
        bot.send_message(game['player2'], result['result'], reply_markup=game_keyboard, parse_mode='Markdown')
        bot.answer_callback_query(call.id, "Матч окончен!", show_alert=True)
        return
    
    if msg:
        bot.answer_callback_query(call.id, msg, show_alert=True)
        return
    
    if result:
        game = result
        game_keyboard = types.InlineKeyboardMarkup(row_width=3)
        btn_shot = types.InlineKeyboardButton(text="🏒 БРОСОК", callback_data=f"match_action_{match_id}_shot")
        btn_pass = types.InlineKeyboardButton(text="🔄 ПАС", callback_data=f"match_action_{match_id}_pass")
        btn_tackle = types.InlineKeyboardButton(text="⚡ ОТБОР", callback_data=f"match_action_{match_id}_tackle")
        game_keyboard.add(btn_shot, btn_pass, btn_tackle)
        
        current_player_name = get_username(game['current_turn'])
        events_text = "\n".join(game['events'][-5:]) if game['events'] else "Матч начался!"
        
        match_text = f"🏒 **МАТЧ**\n\nПериод: {game['period']}/3\nСчет: {game['score1']}:{game['score2']}\n\n{events_text}\n\nХод игрока: @{current_player_name}"
        
        bot.edit_message_text(match_text, call.message.chat.id, call.message.message_id,
                             reply_markup=game_keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "match_history")
def match_history(call):
    user_id = call.from_user.id
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM matches_history 
    WHERE player1_id = ? OR player2_id = ? 
    ORDER BY match_date DESC LIMIT 10''', (user_id, user_id))
    history = cursor.fetchall()
    conn.close()
    
    if not history:
        bot.edit_message_text("📜 **История матчей пуста!**\n\nСыграйте первый матч!", 
                             call.message.chat.id, call.message.message_id,
                             reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')
        return
    
    text = "📜 **ИСТОРИЯ МАТЧЕЙ**\n\n"
    for match in history:
        match_id, p1_id, p2_id, p1_score, p2_score, winner_id, date = match
        p1_name = get_username(p1_id)
        p2_name = get_username(p2_id)
        
        if winner_id == user_id:
            result = "✅ ПОБЕДА"
        else:
            result = "❌ ПОРАЖЕНИЕ"
        
        text += f"🏒 {p1_name} {p1_score}:{p2_score} {p2_name}\n"
        text += f"📊 {result} | {date[:10]}\n\n"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

# ============ ПРОМОКОДЫ ============
@bot.callback_query_handler(func=lambda call: call.data == "promo_menu")
def promo_menu(call):
    keyboard = types.InlineKeyboardMarkup()
    btn_activate = types.InlineKeyboardButton(text="🎫 Активировать промокод", callback_data="activate_promo")
    btn_back = types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    keyboard.add(btn_activate, btn_back)
    
    bot.edit_message_text("🎁 **ПРОМОКОДЫ**\n\nВведите промокод для получения бонуса:", 
                         call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "activate_promo")
def activate_promo(call):
    msg = bot.send_message(call.message.chat.id, "📝 Введите промокод:")
    bot.register_next_step_handler(msg, process_promo_activation, call.message.chat.id, call.message.message_id)

def process_promo_activation(message, chat_id, msg_id):
    code = message.text.strip().upper()
    success, result = activate_promo_code(message.from_user.id, code)
    bot.send_message(message.chat.id, result)
    bot.send_message(chat_id, "🏒 Вернуться в меню:", reply_markup=main_menu_keyboard(message.from_user.id))

# ============ АДМИН-КОМАНДЫ ============
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_add_card = types.InlineKeyboardButton(text="➕ Добавить карточку", callback_data="add_card_start")
    btn_cards_list = types.InlineKeyboardButton(text="📋 Список карточек", callback_data="cards_list")
    btn_backup = types.InlineKeyboardButton(text="💾 Создать бэкап", callback_data="backup_now")
    btn_reset_cd = types.InlineKeyboardButton(text="⏰ Сбросить КД себе", callback_data="reset_my_cd")
    btn_add_promo = types.InlineKeyboardButton(text="🎁 Создать промокод", callback_data="create_promo_start")
    btn_back = types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    keyboard.add(btn_add_card, btn_cards_list, btn_backup, btn_reset_cd, btn_add_promo, btn_back)
    
    bot.edit_message_text("🔧 **АДМИН-ПАНЕЛЬ**\n\nВыберите действие:", 
                         call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "add_card_start")
def add_card_start(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    temp_card_data[call.from_user.id] = {}
    msg = bot.send_message(call.message.chat.id, "📝 Введите **имя игрока**:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_card_name, call.message.chat.id, call.message.message_id)

def process_card_name(message, chat_id, msg_id):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    temp_card_data[user_id] = {'name': message.text.strip()}
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
    for pos_key, pos_info in POSITIONS.items():
        btn = types.InlineKeyboardButton(
            text=f"{pos_info['emoji']} {pos_info['name']}",
            callback_data=f"set_card_position_{pos_key}"
        )
        keyboard.add(btn)
    
    bot.send_message(chat_id, "🎭 Выберите **позицию** игрока:", reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_card_position_'))
def process_card_position(call):
    user_id = call.from_user.id
    position = call.data.split('_')[3]
    
    if user_id not in temp_card_data:
        temp_card_data[user_id] = {}
    
    temp_card_data[user_id]['position'] = position
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for key, rarity in RARITIES.items():
        btn = types.InlineKeyboardButton(
            text=f"{rarity['emoji']} {rarity['name']}",
            callback_data=f"set_card_rarity_{key}"
        )
        keyboard.add(btn)
    
    bot.edit_message_text(
        f"✅ Позиция выбрана: {POSITIONS[position]['emoji']} {POSITIONS[position]['name']}\n\n💎 Теперь выберите **редкость** карточки:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_card_rarity_'))
def process_card_rarity(call):
    user_id = call.from_user.id
    rarity = call.data.split('_')[3]
    
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
        position=data['position'],
        rarity=data['rarity'],
        image_path=data['image_path'],
        added_by=user_id
    )
    
    del temp_card_data[user_id]
    
    card = get_card_by_id(card_id)
    card_text = get_card_text(card)
    
    bot.send_message(chat_id, f"✅ **Карточка успешно добавлена!**\n\n{card_text}\n🆔 ID: {card_id}", parse_mode='Markdown')
    admin_panel_callback(message)

@bot.callback_query_handler(func=lambda call: call.data == "cards_list")
def cards_list_callback(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT card_id, name, team, position, rarity FROM cards ORDER BY card_id")
    cards = cursor.fetchall()
    conn.close()
    
    if not cards:
        bot.edit_message_text("📭 В базе нет карточек.", call.message.chat.id, call.message.message_id,
                             reply_markup=back_to_menu_keyboard())
        return
    
    text = "📋 **СПИСОК КАРТОЧЕК**\n\n"
    for card in cards:
        rarity_info = RARITIES[card[4]]
        pos_info = POSITIONS.get(card[3], POSITIONS['forward'])
        text += f"{rarity_info['emoji']} **ID:{card[0]}** {card[1]} ({card[2]}) — {pos_info['emoji']} {pos_info['name']} — {rarity_info['name']}\n"
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text="🗑️ Удалить карточку", callback_data="delete_card_menu"))
    keyboard.add(types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "delete_card_menu")
def delete_card_menu(call):
    if call.from_user.id not in ADMIN_IDS:
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
        admin_panel_callback(message)
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректный ID карточки!")

@bot.callback_query_handler(func=lambda call: call.data == "backup_now")
def backup_now_callback(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    try:
        if not os.path.exists('backups'):
            os.makedirs('backups')
        
        backup_name = f"backups/hockey_cards_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2('hockey_cards.db', backup_name)
        
        with open(backup_name, 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption=f"✅ Бэкап создан: {backup_name}")
        
        bot.answer_callback_query(call.id, "✅ Бэкап создан!", show_alert=True)
        admin_panel_callback(call)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {e}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "reset_my_cd")
def reset_my_cd_callback(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    conn = sqlite3.connect('hockey_cards.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_card_time = NULL WHERE user_id = ?", (call.from_user.id,))
    conn.commit()
    conn.close()
    
    bot.answer_callback_query(call.id, "✅ Ваш КД сброшен!", show_alert=True)
    admin_panel_callback(call)

@bot.callback_query_handler(func=lambda call: call.data == "create_promo_start")
def create_promo_start(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав!", show_alert=True)
        return
    
    msg = bot.send_message(call.message.chat.id, "📝 Введите **код промокода**:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_promo_code, call.message.chat.id, call.message.message_id)

def process_promo_code(message, chat_id, msg_id):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    temp_promo_data[user_id] = {'code': message.text.strip().upper()}
    msg = bot.send_message(chat_id, "💰 Введите **сумму бонуса**:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_promo_reward, chat_id, msg_id)

def process_promo_reward(message, chat_id, msg_id):
    user_id = message.from_user.id
    try:
        reward = int(message.text.strip())
        temp_promo_data[user_id]['reward'] = reward
        msg = bot.send_message(chat_id, "📅 Введите **срок действия (дни)**:", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_promo_days, chat_id, msg_id)
    except:
        bot.send_message(chat_id, "❌ Введите число!")

def process_promo_days(message, chat_id, msg_id):
    user_id = message.from_user.id
    try:
        days = int(message.text.strip())
        temp_promo_data[user_id]['days'] = days
        msg = bot.send_message(chat_id, "👥 Введите **лимит использований**:", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_promo_limit, chat_id, msg_id)
    except:
        bot.send_message(chat_id, "❌ Введите число!")

def process_promo_limit(message, chat_id, msg_id):
    user_id = message.from_user.id
    try:
        limit = int(message.text.strip())
        data = temp_promo_data[user_id]
        
        create_promo_code(data['code'], data['reward'], data['days'], limit)
        
        bot.send_message(chat_id, f"✅ **Промокод создан!**\n\nКод: `{data['code']}`\n💰 Сумма: {data['reward']} ₽\n📅 Дней: {data['days']}\n👥 Лимит: {limit}", parse_mode='Markdown')
        del temp_promo_data[user_id]
        admin_panel_callback(message)
        
    except:
        bot.send_message(chat_id, "❌ Введите число!")

# ============ ВЕБ-СЕРВЕР ДЛЯ RENDER ============
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "🏒 Cards MHL Bot is running! 🎴"

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
    print("🤖 Бот карточек МХЛ запущен!")
    print("💎 Редкости: Обычная (45%), Редкая (25%), Эпическая (15%), Мифическая (10%), Легендарная (5%)")
    print("⏰ КД на открытие: 2 ЧАСА")
    print(f"👑 Количество админов: {len(ADMIN_IDS)}")
    print("🎮 Все кнопки - инлайн!")
    print("⭐ Добавлен профиль с позицией и составом!")
    print("🏒 Матчи 1 на 1 с учетом позиций и состава!")
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")
            time.sleep(10)
