import telebot
import json
from transliterate import translit
from Levenshtein import ratio
import speech_recognition as sr
from io import BytesIO
import uuid
import os
import requests
import subprocess
from datetime import datetime, timedelta

def load_settings():
    try:
        with open('settings.json', 'r', encoding='utf-8') as file:
            settings = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {
            "token": "YOUR_BOT_API_KEY",
            "admins": [""],
            "ban_words": [],
            "bot_active": True,
            "check_message_active": "Ебашу на благо кого-то! ",
            "check_message_inactive": "Чилю",
            "match_threshold": 0.65
        }
        save_settings(settings)
    return settings

def save_settings(settings):
    with open('settings.json', 'w', encoding='utf-8') as file:
        json.dump(settings, file, ensure_ascii=False, indent=4)

def load_statistics():
    try:
        with open('stat_chat.json', 'r', encoding='utf-8') as file:
            stats = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        stats = {
            "messages": [],
            "users": {}
        }
        save_statistics(stats)
    return stats

def save_statistics(stats):
    with open('stat_chat.json', 'w', encoding='utf-8') as file:
        json.dump(stats, file, ensure_ascii=False, indent=4)

settings = load_settings()
stats = load_statistics()
admins = settings["admins"]
ban_words = settings["ban_words"]
bot_active = settings.get("bot_active", True)

bot = telebot.TeleBot(settings["token"])

def contains_banned_word(text, ban_words, threshold):
    text_lower = text.lower()
    transliterated_text = translit(text_lower, 'ru')
    for ban_word in ban_words:
        if ban_word in text_lower or ban_word in transliterated_text:
            return True
        for word in text_lower.split():
            if ratio(word, ban_word) > threshold or ratio(translit(word, 'ru'), ban_word) > threshold:
                return True
    return False

@bot.message_handler(content_types=['text'])
def worker(message):
    global bot_active
    message_text = message.text.lower()
    if message_text == '/banwords' and str(message.from_user.id) in admins:
        bot.send_message(message.chat.id, ' ; '.join(ban_words))
        return
    if message_text == '/off' and str(message.from_user.id) in admins:
        bot_active = False
        settings["bot_active"] = bot_active
        save_settings(settings)
        bot.send_message(message.chat.id, "Бот отключен.")
        return

    if message_text == '/on' and str(message.from_user.id) in admins:
        bot_active = True
        settings["bot_active"] = bot_active
        save_settings(settings)
        bot.send_message(message.chat.id, "Бот включен.")
        return

    if message_text == '/check':
        if bot_active:
            bot.send_message(message.chat.id, settings["check_message_active"])
        else:
            bot.send_message(message.chat.id, settings["check_message_inactive"])
        return

    if message_text == '/stat' and str(message.from_user.id) in admins:
        send_chat_statistics(message.chat.id)
        return

    if not bot_active:
        return

    if message_text.startswith('/add_banword') and str(message.from_user.id) in admins:
        parts = message_text.split(maxsplit=1)
        if len(parts) > 1:
            new_word = parts[1].strip().lower()
            if new_word not in ban_words:
                ban_words.append(new_word)
                settings["ban_words"] = ban_words
                save_settings(settings)
                bot.send_message(message.chat.id, f"Слово '{new_word}' добавлено в список запрещённых.")
            else:
                bot.send_message(message.chat.id, f"Слово '{new_word}' уже есть в списке запрещённых.")
        else:
            bot.send_message(message.chat.id, "Использование: /add_banword <слово>")
        return

    if message_text.startswith('/del_banword') and str(message.from_user.id) in admins:
        parts = message_text.split(maxsplit=1)
        if len(parts) > 1:
            word_to_remove = parts[1].strip().lower()
            if word_to_remove in ban_words:
                ban_words.remove(word_to_remove)
                settings["ban_words"] = ban_words
                save_settings(settings)
                bot.send_message(message.chat.id, f"Слово '{word_to_remove}' удалено из списка запрещённых.")
            else:
                bot.send_message(message.chat.id, f"Слова '{word_to_remove}' нет в списке запрещённых.")
        else:
            bot.send_message(message.chat.id, "Использование: /del_banword <слово>")
        return

    if message_text == '/add_admin' and str(message.from_user.id) in admins and message.reply_to_message:
        new_admin = str(message.reply_to_message.from_user.id)
        if new_admin not in admins:
            admins.append(new_admin)
            settings["admins"] = admins
            save_settings(settings)
            bot.send_message(message.chat.id, f"Пользователь '{message.reply_to_message.from_user.username}' добавлен в список администраторов.")
        else:
            bot.send_message(message.chat.id, f"Пользователь '{message.reply_to_message.from_user.username}' уже есть в списке администраторов.")
        return

    if message_text == '/del_admin' and str(message.from_user.id) in admins and message.reply_to_message:
        admin_to_remove = str(message.reply_to_message.from_user.id)
        if admin_to_remove in admins:
            admins.remove(admin_to_remove)
            settings["admins"] = admins
            save_settings(settings)
            bot.send_message(message.chat.id, f"Пользователь '{message.reply_to_message.from_user.username}' удален из списка администраторов.")
        else:
            bot.send_message(message.chat.id, f"Пользователя '{message.reply_to_message.from_user.username}' нет в списке администраторов.")
        return

    if message_text.startswith('/del_all') and str(message.from_user.id) in admins and message.reply_to_message:
        del_all_messages(message.chat.id, message.reply_to_message.message_id)
        return

    if message_text.startswith('/mute') and str(message.from_user.id) in admins and message.reply_to_message:
        parts = message_text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].isdigit():
            mute_duration = int(parts[1])
            mute_user(message.chat.id, message.reply_to_message.from_user.id, mute_duration)
            bot.send_message(message.chat.id, f"Пользователь {message.reply_to_message.from_user.username} замьючен на {mute_duration} минут.")
        else:
            bot.send_message(message.chat.id, "Использование: /mute <минуты>")
        return

    if message_text.startswith('/unmute') and str(message.from_user.id) in admins and message.reply_to_message:
        unmute_user(message.chat.id, message.reply_to_message.from_user.id)
        bot.send_message(message.chat.id, f"Пользователь {message.reply_to_message.from_user.username} размьючен.")
        return

    if contains_banned_word(message.text, ban_words, settings["match_threshold"]):
        bot.delete_message(message.chat.id, message.message_id)
    else:
        update_message_statistics(message)

@bot.edited_message_handler(content_types=['text'])
def edited_message_worker(message):
    if bot_active and contains_banned_word(message.text, ban_words, settings["match_threshold"]):
        bot.delete_message(message.chat.id, message.message_id)

@bot.message_handler(content_types=['voice'])
def get_audio_messages(message):
    try:
        file_info = bot.get_file(message.voice.file_id)
        path = file_info.file_path
        fname = os.path.basename(path)
        doc = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(settings["token"], file_info.file_path))
        with open(fname+'.oga', 'wb') as f:
            f.write(doc.content)
        process = subprocess.run(['ffmpeg', '-i', fname+'.oga', fname+'.wav'])
        result = audio_to_text(fname+'.wav')
        if contains_banned_word(result, ban_words, settings["match_threshold"]):
            bot.delete_message(message.chat.id, message.message_id)
    except sr.UnknownValueError as e:
        return
    except Exception as e:
        bot.send_message(message.from_user.id, e)
    finally:
        os.remove(fname+'.wav')
        os.remove(fname+'.oga')

def audio_to_text(dest_name: str):
    r = sr.Recognizer()
    message = sr.AudioFile(dest_name)
    with message as source:
        audio = r.record(source)
    result = r.recognize_google(audio, language="ru_RU")
    return result

def del_all_messages(chat_id, until_message_id):
    try:
        last_message_id = bot.send_message(chat_id, "Удаляю сообщения...").message_id
        for message_id in range(last_message_id, until_message_id, -1):
            try:
                bot.delete_message(chat_id, message_id)
            except Exception as e:
                pass
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка при удалении сообщений: {e}")

def mute_user(chat_id, user_id, duration):
    until_date = datetime.now() + timedelta(minutes=duration)
    bot.restrict_chat_member(chat_id, user_id, can_send_messages=False, until_date=until_date)

def unmute_user(chat_id, user_id):
    bot.restrict_chat_member(chat_id, user_id, can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)

def update_message_statistics(message):
    user_id = str(message.from_user.id)
    timestamp = datetime.now().timestamp()
    stats['messages'].append({
        "user_id": user_id,
        "timestamp": timestamp
    })
    if user_id not in stats['users']:
        stats['users'][user_id] = {
            "username": message.from_user.username,
            "messages_count": 0
        }
    stats['users'][user_id]['messages_count'] += 1
    save_statistics(stats)

def send_chat_statistics(chat_id):
    try:
        chat = bot.get_chat(chat_id)
        members_count = bot.get_chat_members_count(chat_id)
        admins = bot.get_chat_administrators(chat_id)
        admins_usernames = [admin.user.username for admin in admins]

        now = datetime.now()
        one_day_ago = now - timedelta(days=1)
        one_week_ago = now - timedelta(weeks=1)
        one_month_ago = now - timedelta(days=30)

        total_messages = len(stats['messages'])
        messages_today = len([msg for msg in stats['messages'] if datetime.fromtimestamp(msg['timestamp']) > one_day_ago])
        messages_week = len([msg for msg in stats['messages'] if datetime.fromtimestamp(msg['timestamp']) > one_week_ago])
        messages_month = len([msg for msg in stats['messages'] if datetime.fromtimestamp(msg['timestamp']) > one_month_ago])

        top_users = sorted(stats['users'].items(), key=lambda item: item[1]['messages_count'], reverse=True)[:3]
        top_users_info = [f"@{user['username']} ({user['messages_count']} сообщений)" for user_id, user in top_users]

        stats_message = (f" Статистика чта:\n"
                         f"Название: {chat.title}\n"
                         f"Количество участников: {members_count}\n"
                         f"Количество администраторов: {len(admins)}\n"
                         f"Администраторы: {', '.join(admins_usernames)}\n\n"
                         f"Всего сообщений: {total_messages}\n"
                         f"Сообщений за сегодня: {messages_today}\n"
                         f"Сообщений за неделю: {messages_week}\n"
                         f"Сообщений за месяц: {messages_month}\n\n"
                         f"Топ 3 пользователя по количеству сообщений:\n"
                         f"{'; '.join(top_users_info)}")
        bot.send_message(chat_id, stats_message)
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка при получении статистики: {e}")

bot.polling()
