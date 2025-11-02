#!/usr/bin/env python3
# coding: utf-8

"""
UniFriends55 - Telegram бот для знакомств по интересам внутри университета.
Готовая версия для деплоя на Railway.
Не забудь указать переменную окружения BOT_TOKEN в Railway.
"""

import logging
import sqlite3
import os
from typing import List

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN") or "ВАШ_ТОКЕН_ЗДЕСЬ"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

DB_PATH = os.environ.get("DB_PATH", "bot.db")

# Список интересов, адаптированный под студентов Финансового университета Омска
INTERESTS = [
    "Воллейбол",
    "Футбол",
    "Баскетбол",
    "Музыка",
    "IT",
    "Бизнес",
    "Путешествия",
    "Искусство",
    "Самообразование",
    "Языки",
    "Финансы",
    "Кино",
    "Игры",
    "Кофейни",
    "Психология",
    "Фитнес"
]

# Состояния регистрации
class RegStates(StatesGroup):
    name = State()
    age = State()
    faculty = State()
    course = State()
    photo = State()
    interests = State()

# === База данных ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER UNIQUE,
        name TEXT,
        age INTEGER,
        faculty TEXT,
        course TEXT,
        photo_file_id TEXT,
        interests TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        liked_user_id INTEGER,
        UNIQUE(user_id, liked_user_id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shown (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        shown_user_id INTEGER,
        UNIQUE(user_id, shown_user_id)
    )
    """)
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_PATH)

# === Утилиты работы с БД ===
def upsert_user(tg_id: int, name: str = None, age: int = None, faculty: str = None, course: str = None, photo_file_id: str = None, interests: List[str] = None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT tg_id FROM users WHERE tg_id = ?", (tg_id,))
    existing = cur.fetchone()
    if existing:
        fields = []
        params = []
        if name is not None:
            fields.append("name = ?"); params.append(name)
        if age is not None:
            fields.append("age = ?"); params.append(age)
        if faculty is not None:
            fields.append("faculty = ?"); params.append(faculty)
        if course is not None:
            fields.append("course = ?"); params.append(course)
        if photo_file_id is not None:
            fields.append("photo_file_id = ?"); params.append(photo_file_id)
        if interests is not None:
            fields.append("interests = ?"); params.append(",".join(interests))
        if fields:
            sql = "UPDATE users SET " + ", ".join(fields) + " WHERE tg_id = ?"
            params.append(tg_id)
            cur.execute(sql, tuple(params))
    else:
        cur.execute("""
            INSERT INTO users (tg_id, name, age, faculty, course, photo_file_id, interests)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tg_id, name or "", age or 0, faculty or "", course or "", photo_file_id or "", ",".join(interests or [])))
    conn.commit()
    conn.close()

def get_user_by_tg(tg_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, tg_id, name, age, faculty, course, photo_file_id, interests FROM users WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    id_, tg_id, name, age, faculty, course, photo_file_id, interests = row
    interests_list = interests.split(",") if interests else []
    return {"id": id_, "tg_id": tg_id, "name": name, "age": age, "faculty": faculty, "course": course, "photo_file_id": photo_file_id, "interests": interests_list}

def get_all_other_users(tg_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, tg_id, name, age, faculty, course, photo_file_id, interests FROM users WHERE tg_id != ?", (tg_id,))
    rows = cur.fetchall()
    conn.close()
    users = []
    for r in rows:
        id_, tg, name, age, faculty, course, photo_file_id, interests = r
        interests_list = interests.split(",") if interests else []
        users.append({"id": id_, "tg_id": tg, "name": name, "age": age, "faculty": faculty, "course": course, "photo_file_id": photo_file_id, "interests": interests_list})
    return users

def mark_shown(user_id: int, shown_user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO shown (user_id, shown_user_id) VALUES (?, ?)", (user_id, shown_user_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def has_been_shown(user_id: int, shown_user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM shown WHERE user_id = ? AND shown_user_id = ?", (user_id, shown_user_id))
    r = cur.fetchone()
    conn.close()
    return bool(r)

def add_like(user_id: int, liked_user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO likes (user_id, liked_user_id) VALUES (?, ?)", (user_id, liked_user_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def check_mutual_like(user_id: int, liked_user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM likes WHERE user_id = ? AND liked_user_id = ?", (liked_user_id, user_id))
    r = cur.fetchone()
    conn.close()
    return bool(r)

# Подсчёт совпадений интересов
def common_interest_count(a: List[str], b: List[str]) -> int:
    return len(set([x.strip().lower() for x in a if x]) & set([x.strip().lower() for x in b if x]))

# === Keyboards ===
def make_start_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("/find"), KeyboardButton("/profile"))
    kb.add(KeyboardButton("/settings"), KeyboardButton("/help"))
    return kb

def make_interests_keyboard(selected: List[str] = None):
    if selected is None: selected = []
    kb = InlineKeyboardMarkup(row_width=2)
    for interest in INTERESTS:
        text = ("✅ " if interest in selected else "") + interest
        kb.insert(InlineKeyboardButton(text, callback_data=f"toggle_interest||{interest}"))
    kb.row(InlineKeyboardButton("Готово", callback_data="interests_done"))
    return kb

def profile_action_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("❤️ Нравится", callback_data="like"))
    kb.add(InlineKeyboardButton("❌ Пропустить", callback_data="skip"))
    kb.add(InlineKeyboardButton("Пожаловаться", callback_data="report"))
    return kb

# === Хендлеры ===

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message, state: FSMContext):
    init_db()
    user = get_user_by_tg(message.from_user.id)
    if user is None or not user.get("name"):
        await message.answer(
            "Привет! Я UniFriends55 — бот для знакомств и поиска друзей по интересам внутри вашего университета.\nСначала пройдём короткую регистрацию.\nКак тебя зовут?",
            reply_markup=ReplyKeyboardRemove()
        )
        await RegStates.name.set()
    else:
        await message.answer("Рады видеть! Используйте кнопки ниже.", reply_markup=make_start_kb())

@dp.message_handler(state=RegStates.name)
async def reg_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Слишком короткое имя. Введи, пожалуйста, имя (2+ символа).")
        return
    await state.update_data(name=name)
    await message.answer("Сколько тебе лет? (введите число)")
    await RegStates.age.set()

@dp.message_handler(lambda m: not m.text.isdigit(), state=RegStates.age)
async def reg_age_invalid(message: types.Message):
    await message.answer("Пожалуйста, введите возраст цифрами (например, 19).")

@dp.message_handler(lambda m: m.text.isdigit(), state=RegStates.age)
async def reg_age(message: types.Message, state: FSMContext):
    age = int(message.text.strip())
    if age < 16 or age > 100:
        await message.answer("Введи, пожалуйста, реальный возраст (16-100).")
        return
    await state.update_data(age=age)
    await message.answer("Укажи факультет (например: Финансовый факультет):")
    await RegStates.faculty.set()

@dp.message_handler(state=RegStates.faculty)
async def reg_faculty(message: types.Message, state: FSMContext):
    faculty = message.text.strip()
    await state.update_data(faculty=faculty)
    await message.answer("Укажи курс (например: 1, 2, 3 и т.д.):")
    await RegStates.course.set()

@dp.message_handler(lambda m: not m.text.isdigit(), state=RegStates.course)
async def reg_course_invalid(message: types.Message):
    await message.answer("Напиши номер курса цифрами (например: 2).")

@dp.message_handler(lambda m: m.text.isdigit(), state=RegStates.course)
async def reg_course(message: types.Message, state: FSMContext):
    course = message.text.strip()
    await state.update_data(course=course)
    await message.answer("Отправь своё фото (лучше портретное):")
    await RegStates.photo.set()

@dp.message_handler(content_types=['photo'], state=RegStates.photo)
async def reg_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    file_id = photo.file_id
    await state.update_data(photo_file_id=file_id)
    await message.answer("Отлично! Теперь выбери свои интересы. Нажимай, чтобы выбрать / снять. Нажми «Готово», когда закончишь.", reply_markup=make_interests_keyboard([]))
    await RegStates.interests.set()

@dp.message_handler(lambda m: m.text, content_types=types.ContentTypes.ANY, state=RegStates.photo)
async def reg_photo_waiting(message: types.Message):
    await message.answer("Нужно именно фото — отправь, пожалуйста, фото.")

# Коллбэки для интересов
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("toggle_interest||"), state=RegStates.interests)
async def toggle_interest(callback: types.CallbackQuery, state: FSMContext):
    _, interest = callback.data.split("||", 1)
    data = await state.get_data()
    selected = data.get("interests", []) or []
    if interest in selected:
        selected.remove(interest)
    else:
        selected.append(interest)
    await state.update_data(interests=selected)
    await callback.message.edit_reply_markup(reply_markup=make_interests_keyboard(selected))
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "interests_done", state=RegStates.interests)
async def interests_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    name = data.get("name")
    age = data.get("age")
    faculty = data.get("faculty")
    course = data.get("course")
    photo_file_id = data.get("photo_file_id")
    interests = data.get("interests", [])
    # записать в БД
    upsert_user(callback.from_user.id, name=name, age=age, faculty=faculty, course=course, photo_file_id=photo_file_id, interests=interests)
    await callback.message.answer("Регистрация завершена! Теперь используйте /find чтобы искать людей или /profile чтобы посмотреть свой профиль.", reply_markup=make_start_kb())
    await state.finish()
    await callback.answer("Сохранено ✅")

# /profile — показать свой профиль и кнопки редактирования
@dp.message_handler(commands=["profile"])
async def cmd_profile(message: types.Message):
    user = get_user_by_tg(message.from_user.id)
    if not user:
        await message.answer("Профиль не найден — пройди регистрацию через /start.")
        return
    text = f"📋 Профиль:\nИмя: {user['name']}\nВозраст: {user['age']}\nФакультет: {user['faculty']}\nКурс: {user['course']}\nИнтересы: {', '.join(user['interests']) if user['interests'] else '—'}"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("/edit_profile"), KeyboardButton("/find"))
    kb.add(KeyboardButton("/settings"), KeyboardButton("/help"))
    if user.get("photo_file_id"):
        await bot.send_photo(message.chat.id, user['photo_file_id'], caption=text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)

# /edit_profile простые команды
@dp.message_handler(commands=["edit_profile"])
async def cmd_edit_profile(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Изменить имя"), KeyboardButton("Изменить возраст"))
    kb.add(KeyboardButton("Изменить факультет"), KeyboardButton("Изменить курс"))
    kb.add(KeyboardButton("Изменить фото"), KeyboardButton("Изменить интересы"))
    kb.add(KeyboardButton("/profile"))
    await message.answer("Что хотите изменить?", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "Изменить имя")
async def edit_name_start(message: types.Message):
    await message.answer("Введите новое имя:", reply_markup=ReplyKeyboardRemove())
    await RegStates.name.set()

@dp.message_handler(lambda m: m.text == "Изменить возраст")
async def edit_age_start(message: types.Message):
    await message.answer("Введите новый возраст:", reply_markup=ReplyKeyboardRemove())
    await RegStates.age.set()

@dp.message_handler(lambda m: m.text == "Изменить факультет")
async def edit_fac_start(message: types.Message):
    await message.answer("Введите новый факультет/название:", reply_markup=ReplyKeyboardRemove())
    await RegStates.faculty.set()

@dp.message_handler(lambda m: m.text == "Изменить курс")
async def edit_course_start(message: types.Message):
    await message.answer("Введите новый курс (цифрами):", reply_markup=ReplyKeyboardRemove())
    await RegStates.course.set()

@dp.message_handler(lambda m: m.text == "Изменить фото")
async def edit_photo_start(message: types.Message):
    await message.answer("Отправь новое фото:", reply_markup=ReplyKeyboardRemove())
    await RegStates.photo.set()

@dp.message_handler(lambda m: m.text == "Изменить интересы")
async def edit_interests_start(message: types.Message):
    state = dp.current_state(user=message.from_user.id)
    await state.update_data(interests=get_user_by_tg(message.from_user.id).get("interests", []))
    await message.answer("Выбирай интересы. Нажми «Готово», когда закончишь.", reply_markup=make_interests_keyboard(get_user_by_tg(message.from_user.id).get("interests", [])))
    await RegStates.interests.set()

# /find — начать показ профилей
@dp.message_handler(commands=["find"])
async def cmd_find(message: types.Message):
    user = get_user_by_tg(message.from_user.id)
    if not user or not user.get("interests"):
        await message.answer("Чтобы искать людей, нужно заполнить профиль с интересами. Запусти /start и пройди регистрацию.")
        return
    await message.answer("Ищу людей с похожими интересами...")
    await show_next_candidate(message.chat.id, message.from_user.id)

async def show_next_candidate(chat_id: int, tg_user_id: int):
    me = get_user_by_tg(tg_user_id)
    if not me:
        await bot.send_message(chat_id, "Сначала пройдите регистрацию через /start.")
        return
    candidates = get_all_other_users(tg_user_id)
    scored = []
    for c in candidates:
        if has_been_shown(me['id'], c['id']):
            continue
        score = common_interest_count(me.get("interests", []), c.get("interests", []))
        scored.append((score, c))
    if not scored:
        await bot.send_message(chat_id, "Больше нет новых профилей. Попробуй позже или увеличь круг интересов.")
        return
    scored.sort(key=lambda x: x[0], reverse=True)
    score, candidate = scored[0]
    mark_shown(me['id'], candidate['id'])
    text = f"👤 {candidate['name']}, {candidate['age']} лет\n{candidate['faculty']}\nКурс: {candidate.get('course', '')}\n\nИнтересы: {', '.join(candidate.get('interests', []))}\n\nСовпадений по интересам: {score}"
    if candidate.get("photo_file_id"):
        await bot.send_photo(chat_id, candidate['photo_file_id'], caption=text, reply_markup=profile_action_kb())
    else:
        await bot.send_message(chat_id, text, reply_markup=profile_action_kb())

# Кнопки лайка/пропуска/жалобы
@dp.callback_query_handler(lambda c: c.data in ["like", "skip", "report"])
async def profile_action(callback: types.CallbackQuery):
    user = get_user_by_tg(callback.from_user.id)
    if not user:
        await callback.answer("Сначала пройди регистрацию через /start.")
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT shown_user_id FROM shown WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user['id'],))
    row = cur.fetchone()
    conn.close()
    if not row:
        await callback.answer("Нет кандидатов для действия.")
        return
    candidate_id = row[0]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, tg_id, name, age, faculty, course, photo_file_id, interests FROM users WHERE id = ?", (candidate_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        await callback.answer("Кандидат не найден.")
        return
    cand = {"id": r[0], "tg_id": r[1], "name": r[2], "age": r[3], "faculty": r[4], "course": r[5], "photo_file_id": r[6], "interests": r[7].split(",") if r[7] else []}

    if callback.data == "skip":
        await callback.answer("Пропущено.")
        await show_next_candidate(callback.message.chat.id, callback.from_user.id)
        return

    if callback.data == "report":
        await callback.answer("Жалоба отправлена модераторам (симуляция).")
        await bot.send_message(callback.from_user.id, "Спасибо. Мы получим жалобу и рассмотрим пользователя.")
        return

    if callback.data == "like":
        add_like(user['id'], cand['id'])
        if check_mutual_like(user['id'], cand['id']):
            await callback.answer("Это взаимная симпатия! 🎉")
            link_to_candidate = f"tg://user?id={cand['tg_id']}"
            link_to_user = f"tg://user?id={user['tg_id']}"
            msg_to_user = f"У вас совпадение с {cand['name']} ({cand['age']} лет, {cand['faculty']}, курс {cand['course']}).\nНаписать: {link_to_candidate}\nИнтересы: {', '.join(cand['interests'])}"
            msg_to_cand = f"У вас совпадение с {user['name']} ({user['age']} лет, {user['faculty']}, курс {user['course']}).\nНаписать: {link_to_user}\nИнтересы: {', '.join(user['interests'])}"
            try:
                await bot.send_message(user['tg_id'], msg_to_user)
            except Exception as e:
                logger.exception("Ошибка отправки сообщения пользователю при совпадении: %s", e)
            try:
                await bot.send_message(cand['tg_id'], msg_to_cand)
            except Exception as e:
                logger.exception("Ошибка отправки сообщения кандидату при совпадении: %s", e)
            await show_next_candidate(callback.message.chat.id, callback.from_user.id)
            return
        else:
            await callback.answer("Лайк поставлен. Если симпатия взаимная — бот сообщит вам обоим.")
            await show_next_candidate(callback.message.chat.id, callback.from_user.id)
            return

@dp.message_handler(commands=["help", "settings"])
async def cmd_help(message: types.Message):
    text = (
        "Команды:\n"
        "/start — регистрация / начало\n"
        "/find — поиск людей по интересам\n"
        "/profile — показать свой профиль\n"
        "/edit_profile — изменить профиль\n\n"
        "Советы:\n"
        "- Указывай реальные интересы — так вероятность совпадения больше.\n"
        "- При взаимном лайке бот отправит ссылку чтобы написать."
    )
    await message.answer(text, reply_markup=make_start_kb())

@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Не понял. Используй /start, /find или /profile. Для помощи — /help.", reply_markup=make_start_kb())

# === Запуск ===
if __name__ == "__main__":
    init_db()
    executor.start_polling(dp, skip_updates=True)
