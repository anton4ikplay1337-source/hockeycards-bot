import telebot
from telebot import types
import sqlite3
import random
import string
from datetime import datetime, timedelta
import json
import os
import time
import threading
from flask import Flask

# ============ НАСТРОЙКИ (БЕРЕМ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ) ============
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 123456789))
# ===================================================================

bot = telebot.TeleBot(TOKEN)

# ============ СОЗДАНИЕ БАЗЫ ДАННЫХ ============
def init_db():
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 1000.0,
        registration_date TEXT,
        promo_codes_used TEXT DEFAULT '[]'
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS promo_codes (
        code TEXT PRIMARY KEY,
        reward REAL,
        is_active INTEGER DEFAULT 1,
        expiry_date TEXT,
        uses_limit INTEGER DEFAULT 1,
        uses_count INTEGER DEFAULT 0
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        team1 TEXT,
        team2 TEXT,
        match_date TEXT,
        coeff_win1 REAL,
        coeff_win2 REAL,
        coeff_draw REAL,
        status TEXT DEFAULT 'upcoming'
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bets (
        bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        match_id INTEGER,
        bet_type TEXT,
        amount REAL,
        potential_win REAL,
        status TEXT DEFAULT 'active',
        bet_date TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

def add_demo_matches():
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM matches")
    count = cursor.fetchone()[0]
    if count == 0:
        matches = [
            ('ЦСКА', 'СКА', (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M'), 2.1, 2.0, 3.5),
            ('Ак Барс', 'Салават Юлаев', (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d %H:%M'), 1.8, 2.3, 3.2),
            ('Динамо М', 'Локомотив', (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d %H:%M'), 2.2, 1.9, 3.4),
        ]
        cursor.executemany('''
        INSERT INTO matches (team1, team2, match_date, coeff_win1, coeff_win2, coeff_draw)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', matches)
        conn.commit()
    conn.close()

def add_demo_promocodes():
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM promo_codes")
    count = cursor.fetchone()[0]
    if count == 0:
        promos = [
            ('WELCOME100', 100.0, 1, (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'), 100, 0),
            ('HOCKEY50', 50.0, 1, (datetime.now() + timedelta(days=15)).strftime('%Y-%m-%d'), 50, 0),
            ('BONUS200', 200.0, 1, (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'), 20, 0),
        ]
        cursor.executemany('''
        INSERT INTO promo_codes (code, reward, is_active, expiry_date, uses_limit, uses_count)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', promos)
        conn.commit()
    conn.close()

def generate_promo_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def activate_promo_code(user_id, code):
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT reward, is_active, expiry_date, uses_limit, uses_count FROM promo_codes WHERE code = ?', (code,))
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
        return False, "❌ Промокод уже использован максимальное количество раз!"
    cursor.execute("SELECT promo_codes_used FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    if user_data:
        used_codes = json.loads(user_data[0])
        if code in used_codes:
            conn.close()
            return False, "❌ Вы уже использовали этот промокод!"
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, user_id))
    if user_data:
        used_codes = json.loads(user_data[0])
        used_codes.append(code)
        cursor.execute("UPDATE users SET promo_codes_used = ? WHERE user_id = ?", (json.dumps(used_codes), user_id))
    cursor.execute("UPDATE promo_codes SET uses_count = uses_count + 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    return True, f"✅ Промокод активирован! Вы получили {reward} ₽ бонуса!"

def get_active_matches():
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    cursor.execute('''
    SELECT match_id, team1, team2, match_date, coeff_win1, coeff_win2, coeff_draw
    FROM matches WHERE status = 'upcoming' AND match_date > ? ORDER BY match_date
    ''', (now,))
    matches = cursor.fetchall()
    conn.close()
    return matches

# ============ ГЛАВНОЕ МЕНЮ (ИНЛАЙН КНОПКИ) ============
def main_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_matches = types.InlineKeyboardButton(text="🏒 Матчи", callback_data="menu_matches")
    btn_promo = types.InlineKeyboardButton(text="🎁 Промокоды", callback_data="menu_promo")
    btn_balance = types.InlineKeyboardButton(text="💰 Баланс", callback_data="menu_balance")
    btn_bets = types.InlineKeyboardButton(text="📊 Мои ставки", callback_data="menu_bets")
    btn_top = types.InlineKeyboardButton(text="🏆 Топ игроков", callback_data="menu_top")
    keyboard.add(btn_matches, btn_promo, btn_balance, btn_bets, btn_top)
    return keyboard

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        registration_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('INSERT INTO users (user_id, username, registration_date) VALUES (?, ?, ?)', 
                      (user_id, username, registration_date))
        conn.commit()
        welcome_text = "🏒 **Добро пожаловать в HockeyBet Bot!**\n\n🎉 Вам начислен **1000 ₽** на баланс!\n\n📝 Выберите действие в меню ниже:"
    else:
        welcome_text = "🏒 **С возвращением!**\n\n📝 Выберите действие в меню ниже:"
    
    conn.close()
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard(), parse_mode='Markdown')

# ============ ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ ============
@bot.callback_query_handler(func=lambda call: call.data == "menu_matches")
def menu_matches(call):
    matches = get_active_matches()
    
    if not matches:
        bot.edit_message_text("📭 На данный момент нет доступных матчей.", 
                             call.message.chat.id, call.message.message_id,
                             reply_markup=back_to_menu_keyboard())
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for match in matches:
        match_id, team1, team2, match_date, coeff1, coeff2, coeff_draw = match
        btn = types.InlineKeyboardButton(
            text=f"⚡ {team1} vs {team2} | {match_date[:10]}",
            callback_data=f"match_{match_id}"
        )
        keyboard.add(btn)
    
    keyboard.add(types.InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu"))
    bot.edit_message_text("🏒 **Доступные матчи:**", 
                         call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "menu_promo")
def menu_promo(call):
    keyboard = types.InlineKeyboardMarkup()
    btn_activate = types.InlineKeyboardButton(text="🎫 Активировать промокод", callback_data="activate_promo")
    keyboard.add(btn_activate)
    keyboard.add(types.InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu"))
    bot.edit_message_text("🎁 **Введите промокод для активации бонуса:**", 
                         call.message.chat.id, call.message.message_id,
                         reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "menu_balance")
def menu_balance(call):
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (call.from_user.id,))
    balance = cursor.fetchone()[0]
    conn.close()
    
    text = f"💰 **Ваш баланс:** {balance} ₽"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "menu_bets")
def menu_bets(call):
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT m.team1, m.team2, b.bet_type, b.amount, b.potential_win, b.status, b.bet_date
    FROM bets b JOIN matches m ON b.match_id = m.match_id
    WHERE b.user_id = ? ORDER BY b.bet_date DESC LIMIT 10
    ''', (call.from_user.id,))
    bets = cursor.fetchall()
    conn.close()
    
    if not bets:
        text = "📭 У вас пока нет ставок."
    else:
        text = "📊 **Ваши последние ставки:**\n\n"
        for bet in bets:
            team1, team2, bet_type, amount, potential, status, date = bet
            if bet_type == 'win1':
                bet_text = team1
            elif bet_type == 'win2':
                bet_text = team2
            else:
                bet_text = "Ничья"
            status_emoji = "🟡" if status == "active" else "✅" if status == "won" else "❌"
            text += f"{status_emoji} {team1} vs {team2}\n"
            text += f"Ставка: {bet_text} | {amount} ₽\n"
            text += f"Потенц.: {potential} ₽\n"
            text += f"📅 {date[:16]}\n\n"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "menu_top")
def menu_top(call):
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10')
    players = cursor.fetchall()
    conn.close()
    
    if not players:
        text = "📭 Нет игроков."
    else:
        text = "🏆 **ТОП-10 ИГРОКОВ:**\n\n"
        for i, (username, balance) in enumerate(players, 1):
            medal = "🥇 " if i == 1 else "🥈 " if i == 2 else "🥉 " if i == 3 else f"{i}. "
            text += f"{medal}@{username or 'Аноним'} — {balance} ₽\n"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    bot.edit_message_text("🏒 **Главное меню HockeyBet Bot**\n\nВыберите действие:",
                         call.message.chat.id, call.message.message_id,
                         reply_markup=main_menu_keyboard(), parse_mode='Markdown')

def back_to_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu"))
    return keyboard

# ============ ОБРАБОТКА МАТЧЕЙ ============
@bot.callback_query_handler(func=lambda call: call.data.startswith('match_'))
def handle_match(call):
    match_id = int(call.data.split('_')[1])
    
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT team1, team2, match_date, coeff_win1, coeff_win2, coeff_draw
    FROM matches WHERE match_id = ?
    ''', (match_id,))
    match = cursor.fetchone()
    conn.close()
    
    if match:
        team1, team2, match_date, coeff1, coeff2, coeff_draw = match
        
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        btn_win1 = types.InlineKeyboardButton(text=f"🏒 {team1} ({coeff1})", callback_data=f"bet_{match_id}_win1_{coeff1}")
        btn_win2 = types.InlineKeyboardButton(text=f"🏒 {team2} ({coeff2})", callback_data=f"bet_{match_id}_win2_{coeff2}")
        btn_draw = types.InlineKeyboardButton(text=f"🤝 Ничья ({coeff_draw})", callback_data=f"bet_{match_id}_draw_{coeff_draw}")
        btn_back = types.InlineKeyboardButton(text="◀️ Назад к матчам", callback_data="menu_matches")
        keyboard.add(btn_win1, btn_win2, btn_draw, btn_back)
        
        match_info = f"🏒 **{team1} vs {team2}**\n📅 {match_date}\n\n💰 **Коэффициенты:**\n• {team1}: {coeff1}\n• {team2}: {coeff2}\n• Ничья: {coeff_draw}\n\nВыберите исход для ставки:"
        
        bot.edit_message_text(match_info, call.message.chat.id, call.message.message_id,
                             reply_markup=keyboard, parse_mode='Markdown')

# ============ ОБРАБОТКА СТАВОК ============
@bot.callback_query_handler(func=lambda call: call.data.startswith('bet_'))
def place_bet(call):
    data = call.data.split('_')
    match_id = int(data[1])
    bet_type = data[2]
    coeff = float(data[3])
    
    user_data = {
        'match_id': match_id,
        'bet_type': bet_type,
        'coeff': coeff,
        'message_id': call.message.message_id
    }
    
    msg = bot.send_message(call.message.chat.id, "💰 Введите сумму ставки (минимум 10 ₽):")
    bot.register_next_step_handler(msg, process_bet_amount, user_data, call.message.chat.id)

def process_bet_amount(message, user_data, chat_id):
    try:
        amount = float(message.text)
        
        if amount < 10:
            bot.send_message(message.chat.id, "❌ Минимальная сумма ставки - 10 ₽!")
            return
        
        conn = sqlite3.connect('hockey_bets.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        balance = cursor.fetchone()[0]
        
        if amount > balance:
            bot.send_message(message.chat.id, f"❌ Недостаточно средств! Ваш баланс: {balance} ₽")
            conn.close()
            return
        
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, message.from_user.id))
        
        potential_win = amount * user_data['coeff']
        bet_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
        INSERT INTO bets (user_id, match_id, bet_type, amount, potential_win, bet_date)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (message.from_user.id, user_data['match_id'], user_data['bet_type'], amount, potential_win, bet_date))
        
        conn.commit()
        
        cursor.execute("SELECT team1, team2 FROM matches WHERE match_id = ?", (user_data['match_id'],))
        team1, team2 = cursor.fetchone()
        
        bet_type_text = ""
        if user_data['bet_type'] == 'win1':
            bet_type_text = team1
        elif user_data['bet_type'] == 'win2':
            bet_type_text = team2
        else:
            bet_type_text = "Ничья"
        
        conn.close()
        
        result_text = f"✅ **Ставка принята!**\n\n📊 **Информация:**\n• Матч: {team1} vs {team2}\n• Исход: {bet_type_text}\n• Сумма: {amount} ₽\n• Коэффициент: {user_data['coeff']}\n• Потенциальный выигрыш: {potential_win} ₽\n\nУдачи!"
        
        bot.send_message(message.chat.id, result_text, parse_mode='Markdown', reply_markup=back_to_menu_keyboard())
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректную сумму!")

# ============ АКТИВАЦИЯ ПРОМОКОДА ============
@bot.callback_query_handler(func=lambda call: call.data == "activate_promo")
def activate_promo_menu(call):
    msg = bot.send_message(call.message.chat.id, "📝 Введите промокод:")
    bot.register_next_step_handler(msg, process_promo_activation, call.message.chat.id, call.message.message_id)

def process_promo_activation(message, chat_id, original_msg_id):
    code = message.text.strip().upper()
    success, result = activate_promo_code(message.from_user.id, code)
    
    try:
        bot.delete_message(chat_id, original_msg_id)
    except:
        pass
    
    bot.send_message(message.chat.id, result, reply_markup=back_to_menu_keyboard())

# ============ АДМИН-КОМАНДЫ ============
@bot.message_handler(commands=['players'])
def show_all_players(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(balance) FROM users")
    total_balance = cursor.fetchone()[0] or 0
    cursor.execute("SELECT user_id, username, balance, registration_date FROM users ORDER BY balance DESC")
    players = cursor.fetchall()
    conn.close()
    if not players:
        bot.send_message(message.chat.id, "📭 Нет игроков.")
        return
    text = f"👥 ИГРОКИ: {total}\n💰 Общий баланс: {total_balance} ₽\n📈 Средний: {total_balance/total:.0f} ₽\n\n"
    for i, (uid, name, bal, reg) in enumerate(players, 1):
        medal = "🥇 " if i == 1 else "🥈 " if i == 2 else "🥉 " if i == 3 else f"{i}. "
        text += f"{medal}@{name or 'аноним'} — {bal} ₽\n"
    bot.send_message(message.chat.id, text[:4000])

@bot.message_handler(commands=['addmoney'])
def add_money(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.send_message(message.chat.id, "❌ /addmoney @user 100")
            return
        user_input = parts[1].replace('@', '')
        amount = float(parts[2])
        conn = sqlite3.connect('hockey_bets.db')
        cursor = conn.cursor()
        if user_input.isdigit():
            cursor.execute("SELECT user_id, username FROM users WHERE user_id = ?", (int(user_input),))
        else:
            cursor.execute("SELECT user_id, username FROM users WHERE username = ?", (user_input,))
        user = cursor.fetchone()
        if not user:
            bot.send_message(message.chat.id, f"❌ Пользователь не найден!")
            conn.close()
            return
        uid, name = user
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, uid))
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        new_bal = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ @{name} +{amount} ₽\n💰 Новый баланс: {new_bal} ₽")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(commands=['removemoney'])
def remove_money(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.send_message(message.chat.id, "❌ /removemoney @user 100")
            return
        user_input = parts[1].replace('@', '')
        amount = float(parts[2])
        conn = sqlite3.connect('hockey_bets.db')
        cursor = conn.cursor()
        if user_input.isdigit():
            cursor.execute("SELECT user_id, username, balance FROM users WHERE user_id = ?", (int(user_input),))
        else:
            cursor.execute("SELECT user_id, username, balance FROM users WHERE username = ?", (user_input,))
        user = cursor.fetchone()
        if not user:
            bot.send_message(message.chat.id, f"❌ Пользователь не найден!")
            conn.close()
            return
        uid, name, bal = user
        if bal < amount:
            bot.send_message(message.chat.id, f"❌ У @{name} только {bal} ₽")
            conn.close()
            return
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, uid))
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        new_bal = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ @{name} -{amount} ₽\n💰 Новый баланс: {new_bal} ₽")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(commands=['addmatch'])
def add_match(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 8:
            bot.send_message(message.chat.id, "❌ /addmatch Ком1 Ком2 ГГГГ-ММ-ДД ЧЧ:ММ Коэф1 Коэф2 КоэфНичья")
            return
        team1, team2, date, time, c1, c2, c3 = parts[1], parts[2], parts[3], parts[4], float(parts[5]), float(parts[6]), float(parts[7])
        match_date = f"{date} {time}"
        conn = sqlite3.connect('hockey_bets.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO matches (team1, team2, match_date, coeff_win1, coeff_win2, coeff_draw) VALUES (?, ?, ?, ?, ?, ?)',
                      (team1, team2, match_date, c1, c2, c3))
        conn.commit()
        mid = cursor.lastrowid
        conn.close()
        bot.send_message(message.chat.id, f"✅ Матч добавлен! ID: {mid}\n🏒 {team1} vs {team2}\n📅 {match_date}")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(commands=['allmatches'])
def admin_all_matches(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute("SELECT match_id, team1, team2, match_date, status FROM matches ORDER BY match_date DESC")
    matches = cursor.fetchall()
    conn.close()
    if not matches:
        bot.send_message(message.chat.id, "📭 Нет матчей.")
        return
    text = "📋 ВСЕ МАТЧИ:\n\n"
    for m in matches:
        emoji = "🟢" if m[4] == "upcoming" else "🔴" if m[4] == "finished" else "❌"
        text += f"{emoji} ID:{m[0]} {m[1]} vs {m[2]}\n   📅 {m[3]}\n   {m[4]}\n\n"
    bot.send_message(message.chat.id, text[:4000])

@bot.message_handler(commands=['finishmatch'])
def finish_match(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.send_message(message.chat.id, "❌ /finishmatch ID 1/2/draw")
            return
        mid = int(parts[1])
        res = parts[2].lower()
        conn = sqlite3.connect('hockey_bets.db')
        cursor = conn.cursor()
        cursor.execute("SELECT team1, team2, status FROM matches WHERE match_id = ?", (mid,))
        match = cursor.fetchone()
        if not match:
            bot.send_message(message.chat.id, "❌ Матч не найден!")
            conn.close()
            return
        t1, t2, status = match
        if status != "upcoming":
            bot.send_message(message.chat.id, "❌ Матч уже завершен/отменен!")
            conn.close()
            return
        win_type = None
        if res == "1":
            win_type = "win1"
        elif res == "2":
            win_type = "win2"
        elif res == "draw":
            win_type = "draw"
        else:
            bot.send_message(message.chat.id, "❌ Результат: 1, 2 или draw")
            conn.close()
            return
        cursor.execute("SELECT bet_id, user_id, bet_type, amount, potential_win FROM bets WHERE match_id = ? AND status = 'active'", (mid,))
        bets = cursor.fetchall()
        winners, payout = 0, 0
        for bet in bets:
            bid, uid, btype, amt, pot = bet
            if btype == win_type:
                winners += 1
                payout += pot
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (pot, uid))
                cursor.execute("UPDATE bets SET status = 'won' WHERE bet_id = ?", (bid,))
                try:
                    bot.send_message(uid, f"🎉 ПОБЕДА! Вы выиграли {pot} ₽")
                except:
                    pass
            else:
                cursor.execute("UPDATE bets SET status = 'lost' WHERE bet_id = ?", (bid,))
        cursor.execute("UPDATE matches SET status = 'finished' WHERE match_id = ?", (mid,))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ Матч завершен!\n🏒 {t1} vs {t2}\n📊 Ставок: {len(bets)}, Выиграли: {winners}, Выплата: {payout} ₽")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(commands=['cancelmatch'])
def cancel_match(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /cancelmatch ID")
            return
        mid = int(parts[1])
        conn = sqlite3.connect('hockey_bets.db')
        cursor = conn.cursor()
        cursor.execute("SELECT team1, team2, status FROM matches WHERE match_id = ?", (mid,))
        match = cursor.fetchone()
        if not match:
            bot.send_message(message.chat.id, "❌ Матч не найден!")
            conn.close()
            return
        t1, t2, status = match
        if status != "upcoming":
            bot.send_message(message.chat.id, "❌ Матч нельзя отменить!")
            conn.close()
            return
        cursor.execute("SELECT bet_id, user_id, amount FROM bets WHERE match_id = ? AND status = 'active'", (mid,))
        bets = cursor.fetchall()
        refund = 0
        for bet in bets:
            bid, uid, amt = bet
            refund += amt
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, uid))
            cursor.execute("UPDATE bets SET status = 'cancelled' WHERE bet_id = ?", (bid,))
            try:
                bot.send_message(uid, f"🔄 Матч отменен! Возвращено {amt} ₽")
            except:
                pass
        cursor.execute("UPDATE matches SET status = 'cancelled' WHERE match_id = ?", (mid,))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"🔄 Матч отменен!\n🏒 {t1} vs {t2}\n💰 Возвращено: {refund} ₽")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(commands=['createpromo'])
def create_promo(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ /createpromo сумма [дни] [лимит]")
            return
        reward = float(parts[1])
        days = int(parts[2]) if len(parts) >= 3 else 7
        limit = int(parts[3]) if len(parts) >= 4 else 1
        code = generate_promo_code()
        expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        conn = sqlite3.connect('hockey_bets.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO promo_codes (code, reward, expiry_date, uses_limit) VALUES (?, ?, ?, ?)", (code, reward, expiry, limit))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ Промокод: {code}\n💰 {reward} ₽\n📅 До {expiry}\n👥 {limit} раз")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(commands=['allpromos'])
def all_promos(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    conn = sqlite3.connect('hockey_bets.db')
    cursor = conn.cursor()
    cursor.execute("SELECT code, reward, expiry_date, uses_count, uses_limit, is_active FROM promo_codes ORDER BY expiry_date DESC")
    promos = cursor.fetchall()
    conn.close()
    if not promos:
        bot.send_message(message.chat.id, "📭 Нет промокодов.")
        return
    text = "🎁 ПРОМОКОДЫ:\n\n"
    for p in promos:
        status = "🟢" if p[5] and datetime.now() <= datetime.strptime(p[2], '%Y-%m-%d') else "🔴"
        text += f"{status} {p[0]}: {p[1]}₽ | {p[3]}/{p[4]} | до {p[2]}\n"
    bot.send_message(message.chat.id, text[:4000])

# ============ ДЛЯ RENDER (ВЕБ-СЕРВЕР ДЛЯ ПОДДЕРЖАНИЯ АКТИВНОСТИ) ============
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "🏒 HockeyBot is running 24/7 on Render!"

@flask_app.route('/ping')
def ping():
    return "pong"

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

# Запускаем веб-сервер в отдельном потоке
threading.Thread(target=run_flask, daemon=True).start()
print("🌐 Веб-сервер запущен на порту 8080")
# =======================================================================

# ============ ЗАПУСК БОТА ============
if __name__ == '__main__':
    init_db()
    add_demo_matches()
    add_demo_promocodes()
    print("🤖 Бот успешно запущен на Render!")
    print("✅ Все кнопки работают через инлайн-меню!")
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")
            time.sleep(10)