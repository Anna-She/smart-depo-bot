import sqlite3
import logging
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)

# Включаем логирование
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Состояния диалогов
(
    SELECT_SUBJECT,
    SELECT_TOPIC,
    UPLOAD_SUBJECT,
    UPLOAD_EXISTING_SUBJECT,
    UPLOAD_TOPIC,
    UPLOAD_FILE,
    SEARCH_FILE_NAME,
    DELETE_MATERIAL_SELECT_SUBJECT,
    DELETE_MATERIAL_SELECT_TOPIC,
    DELETE_MATERIAL_SELECT_FILE,
    REPLACE_MATERIAL_SELECT_SUBJECT,
    REPLACE_MATERIAL_SELECT_TOPIC,
    REPLACE_MATERIAL_SELECT_FILE,
    REPLACE_MATERIAL_NEW_FILE,
    VIEW_TOPICS_SUBJECT
) = range(15)

# Подключение к БД
def get_db_connection():
    conn = sqlite3.connect('materials.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Инициализация БД
def init_db():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY,
            topic_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            telegram_file_id TEXT NOT NULL,
            uploaded_by INTEGER,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            downloads_count INTEGER DEFAULT 0,  -- ✅ Новое поле
            FOREIGN KEY (topic_id) REFERENCES topics(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

# Проверка, является ли пользователь преподавателем
def is_teacher(user_id):
    conn = get_db_connection()
    cur = conn.execute('SELECT 1 FROM teachers WHERE user_id = ?', (user_id,))
    res = cur.fetchone()
    conn.close()
    return res is not None

# --- Обработчики ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_teacher(user.id):
        text = (
            "Привет, преподаватель! Здесь ты можешь:\n\n"
            "📚 Найти материал\n"
            "➕ Добавить материал\n"
            "🔍 Поиск по теме/предмету\n"
            "🗑 Удалить/заменить материал\n"
            "📋 Просмотр тем в предмете\n"
            "📈 Статистика скачиваний"
        )
        keyboard = [
            ['📚 Найти материал'],
            ['➕ Добавить материал'],
            ['🔍 Поиск по теме/предмету'],
            ['🗑 Удалить/заменить материал'],
            ['📋 Просмотр тем в предмете'],
            ['📈 Статистика скачиваний']
        ]

    else:
        text = (
            "Привет, студент! Здесь ты можешь:\n\n"
            "📚 Найти материал\n"
            "🔍 Поиск по теме/предмету\n\n"
            "Если ты преподаватель — обратись к администратору бота."
        )
        keyboard = [
            ['📚 Найти материал'],
            ['🔍 Поиск по теме/предмету']
        ]
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню без приветствия"""
    user = update.effective_user
    if is_teacher(user.id):
        text = "Продолжим?"
        keyboard = [
            ['📚 Найти материал'],
            ['➕ Добавить материал'],
            ['🔍 Поиск по теме/предмету'],
            ['🗑 Удалить/заменить материал'],
            ['📋 Просмотр тем в предмете'],
            ['📈 Статистика скачиваний']
        ]

    else:
        text = "Продолжим?"
        keyboard = [
            ['📚 Найти материал'],
            ['🔍 Поиск по теме/предмету']
        ]
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# --- Просмотр статистики скачиваний ---
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает топ скачиваний"""
    if not is_teacher(update.effective_user.id):
        await update.message.reply_text("Только преподаватели могут просматривать статистику.")
        return

    conn = get_db_connection()
    stats = conn.execute(
        '''
        SELECT m.file_name, m.downloads_count, t.name as topic_name, s.name as subject_name
        FROM materials m
        JOIN topics t ON m.topic_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        ORDER BY m.downloads_count DESC
        LIMIT 10
        '''
    ).fetchall()
    conn.close()

    if not stats:
        await update.message.reply_text("Нет данных по скачиваниям.")
        return

    stats_list = '\n'.join([f'{i+1}. {s["file_name"]} ({s["downloads_count"]} скачиваний) — {s["subject_name"]}/{s["topic_name"]}' for i, s in enumerate(stats)])
    await update.message.reply_text(f"📊 Топ скачиваний:\n{stats_list}")
    await menu(update, context)

# --- Команда /add_teacher ---
async def add_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    OWNER_ID = int(os.getenv("OWNER_ID", 0))  # 0 — если не найден
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Доступ запрещён.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /add_teacher <user_id>")
        return
    try:
        user_id = int(context.args[0])
        conn = get_db_connection()
        conn.execute('INSERT OR IGNORE INTO teachers (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Пользователь {user_id} теперь преподаватель.")
    except ValueError:
        await update.message.reply_text("Неверный ID.")

# --- Студент: найти материал ---
async def find_material(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    subjects = conn.execute('SELECT id, name FROM subjects').fetchall()
    conn.close()
    if not subjects:
        await update.message.reply_text("Нет доступных предметов.")
        return ConversationHandler.END
    keyboard = [[s['name']] for s in subjects]
    await update.message.reply_text(
        "Выберите предмет:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return SELECT_SUBJECT

async def select_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject_name = update.message.text.strip()
    conn = get_db_connection()
    subject = conn.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,)).fetchone()
    if not subject:
        await update.message.reply_text("Предмет не найден.")
        return ConversationHandler.END
    context.user_data['subject_id'] = subject['id']
    topics = conn.execute('SELECT name FROM topics WHERE subject_id = ?', (subject['id'],)).fetchall()
    conn.close()
    if not topics:
        await update.message.reply_text("Нет тем по этому предмету.")
        return ConversationHandler.END
    keyboard = [[t['name']] for t in topics]
    await update.message.reply_text(
        "Выберите тему:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return SELECT_TOPIC

async def select_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic_name = update.message.text.strip()
    subject_id = context.user_data['subject_id']
    conn = get_db_connection()
    topic = conn.execute(
        'SELECT id FROM topics WHERE subject_id = ? AND LOWER(name) = LOWER(?)',
        (subject_id, topic_name)
    ).fetchone()
    if not topic:
        await update.message.reply_text("Тема не найдена.")
        await menu(update, context)  # ✅ Возвращаемся к меню
        return ConversationHandler.END
    materials = conn.execute(
        'SELECT id, file_name, telegram_file_id FROM materials WHERE topic_id = ?',
        (topic['id'],)
    ).fetchall()
    conn.close()
    if not materials:
        await update.message.reply_text("Нет материалов по этой теме.")
    else:
        for mat in materials:
            file_name = mat['file_name']
            if file_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                await update.message.reply_photo(photo=mat['telegram_file_id'])
            elif file_name.lower().endswith(('.mp4', '.avi', '.mov')):
                await update.message.reply_video(video=mat['telegram_file_id'])
            else:
                await update.message.reply_document(
                    document=mat['telegram_file_id'],
                    filename=mat['file_name']
                )
            # Увеличиваем счётчик скачиваний
            conn = get_db_connection()
            conn.execute(
                'UPDATE materials SET downloads_count = downloads_count + 1 WHERE id = ?',
                (mat['id'],)
            )
            conn.commit()
            conn.close()

    await menu(update, context)  # ✅ Возвращаемся к меню
    return ConversationHandler.END  # ✅ Завершаем диалог

# --- Преподаватель: добавить материал ---
async def add_material(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_teacher(update.effective_user.id):
        await update.message.reply_text("Только преподаватели могут загружать материалы.")
        return ConversationHandler.END
    conn = get_db_connection()
    subjects = conn.execute('SELECT name FROM subjects').fetchall()
    conn.close()
    keyboard = [[s['name']] for s in subjects] + [['➕ Новый предмет']]
    await update.message.reply_text(
        "Выберите предмет или создайте новый:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return UPLOAD_SUBJECT

async def upload_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '➕ Новый предмет':
        await update.message.reply_text("Введите название нового предмета:", reply_markup=ReplyKeyboardRemove())
        return UPLOAD_EXISTING_SUBJECT
    else:
        # Это выбор существующего предмета
        conn = get_db_connection()
        subject = conn.execute('SELECT id FROM subjects WHERE name = ?', (text,)).fetchone()
        conn.close()
        if not subject:
            await update.message.reply_text("Предмет не найден. Попробуйте снова.")
            return UPLOAD_SUBJECT
        context.user_data['subject_id'] = subject['id']
        await update.message.reply_text("Введите название темы:")
        return UPLOAD_TOPIC

async def upload_existing_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject_name = update.message.text.strip()
    if not subject_name:
        await update.message.reply_text("Некорректное название. Попробуйте снова.")
        return UPLOAD_EXISTING_SUBJECT
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO subjects (name) VALUES (?)', (subject_name,))
        conn.commit()
        subject = conn.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,)).fetchone()
        context.user_data['subject_id'] = subject['id']
        await update.message.reply_text("Теперь введите название темы:")
        return UPLOAD_TOPIC
    except sqlite3.IntegrityError:
        await update.message.reply_text("Предмет уже существует. Введите другое название.")
        return UPLOAD_EXISTING_SUBJECT
    finally:
        conn.close()

async def upload_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic_name = update.message.text.strip()
    if not topic_name:
        await update.message.reply_text("Название темы не может быть пустым. Попробуйте снова.")
        return UPLOAD_TOPIC

    subject_id = context.user_data['subject_id']
    conn = get_db_connection()
    try:
        # Проверяем, существует ли тема
        existing_topic = conn.execute(
            'SELECT id FROM topics WHERE subject_id = ? AND LOWER(name) = LOWER(?)',
            (subject_id, topic_name)
        ).fetchone()

        if existing_topic:
            # Тема уже существует — используем её ID
            topic_id = existing_topic['id']
            await update.message.reply_text(f"✅ Тема '{topic_name}' уже существует. Файл будет добавлен туда.")
        else:
            # Тема не существует — создаём новую
            conn.execute('INSERT INTO topics (subject_id, name) VALUES (?, ?)', (subject_id, topic_name))
            topic_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.commit()
            await update.message.reply_text(f"✅ Тема '{topic_name}' создана. Теперь отправьте файл.")

        context.user_data['topic_id'] = topic_id
        await update.message.reply_text("Отправьте файл (PDF, DOC, PPT, фото, видео и т.д.):")
        return UPLOAD_FILE
    except Exception as e:
        logging.error(f"Ошибка при создании/поиске темы: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте снова.")
        return ConversationHandler.END
    finally:
        conn.close()

async def upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    document = update.message.document
    photo = update.message.photo
    video = update.message.video

    if not document and not photo and not video:
        await update.message.reply_text("Пожалуйста, отправьте файл, фото или видео.")
        return UPLOAD_FILE

    # Определяем тип файла
    if photo:
        photo_obj = photo[-1]
        file_id = photo_obj.file_id
        # Спрашиваем название файла
        await update.message.reply_text("Введите название файла (например: 'Лекция 1'): ")
        context.user_data['temp_file_id'] = file_id  # ✅ Сохраняем ID файла
        context.user_data['temp_file_type'] = 'photo'  # ✅ Тип файла
        return UPLOAD_FILE  # ⚠️ Переход к следующему шагу — ввод названия

    elif video:
        video_obj = video
        file_id = video_obj.file_id
        # Спрашиваем название файла
        await update.message.reply_text("Введите название файла (например: 'Видеоурок'): ")
        context.user_data['temp_file_id'] = file_id  # ✅ Сохраняем ID файла
        context.user_data['temp_file_type'] = 'video'  # ✅ Тип файла
        return UPLOAD_FILE  # ⚠️ Переход к следующему шагу — ввод названия

    elif document:
        # Это документ — проверяем формат
        file_name = document.file_name or "material.dat"
        mime_type = document.mime_type or ""

        allowed_extensions = ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.txt']
        allowed_mimes = [
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'text/plain',
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/webp',
            'video/mp4',
            'video/avi',
            'video/mov',
            'video/wmv',
            'video/flv',
            'video/mpeg',
        ]

        # Проверка формата — только если есть имя файла
        if document.file_name:  # Только если пользователь отправил с именем
            valid_extension = any(file_name.lower().endswith(ext) for ext in allowed_extensions)
            valid_mime = mime_type in allowed_mimes

            if not (valid_extension or valid_mime):
                await update.message.reply_text("❌ Неверный формат файла. Допустимые форматы: PDF, DOC, PPT, TXT, JPG, PNG, MP4 и др.")
                return UPLOAD_FILE
        # Если имени файла нет — разрешаем (это может быть фото/видео без имени)

        file_id = document.file_id

        topic_id = context.user_data.get('topic_id')
        if not topic_id:
            await update.message.reply_text("❌ Тема не была создана. Попробуйте снова.")
            return ConversationHandler.END

        conn = get_db_connection()
        try:
            conn.execute(
                'INSERT INTO materials (topic_id, file_name, telegram_file_id, uploaded_by) VALUES (?, ?, ?, ?)',
                (topic_id, file_name, file_id, user.id)
            )
            conn.commit()
            await update.message.reply_text("✅ Материал успешно сохранён!")
        except Exception as e:
            logging.error(f"Ошибка при сохранении материала: {e}")
            await update.message.reply_text("❌ Произошла ошибка при сохранении файла. Попробуйте снова.")
        finally:
            conn.close()

        await menu(update, context)  # ✅ Возвращаемся к главному меню
        return ConversationHandler.END

# --- Новая функция: ввод названия файла ---
async def ask_for_file_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг: пользователь вводит название файла для фото/видео"""
    file_name = update.message.text.strip()
    if not file_name:
        await update.message.reply_text("Название файла не может быть пустым. Попробуйте снова.")
        return UPLOAD_FILE

    # Получаем ID файла и тип
    file_id = context.user_data.get('temp_file_id')
    file_type = context.user_data.get('temp_file_type')

    if not file_id or not file_type:
        await update.message.reply_text("❌ Не удалось сохранить файл. Попробуйте снова.")
        return ConversationHandler.END

    # Определяем расширение
    if file_type == 'photo':
        file_name += '.jpg'
    elif file_type == 'video':
        file_name += '.mp4'

    topic_id = context.user_data.get('topic_id')
    if not topic_id:
        await update.message.reply_text("❌ Тема не была создана. Попробуйте снова.")
        return ConversationHandler.END

    user = update.effective_user
    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO materials (topic_id, file_name, telegram_file_id, uploaded_by) VALUES (?, ?, ?, ?)',
            (topic_id, file_name, file_id, user.id)
        )
        conn.commit()
        await update.message.reply_text(f"✅ Материал '{file_name}' успешно сохранён!")
    except Exception as e:
        logging.error(f"Ошибка при сохранении фото/видео: {e}")
        await update.message.reply_text("❌ Произошла ошибка при сохранении файла. Попробуйте снова.")
    finally:
        conn.close()

    # Очищаем временные данные
    context.user_data.pop('temp_file_id', None)
    context.user_data.pop('temp_file_type', None)

    await menu(update, context)  # ✅ Возвращаемся к главному меню
    return ConversationHandler.END

# --- Поиск по теме/предмету ---
async def search_by_topic_or_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите название темы, предмета или часть названия:")
    return SEARCH_FILE_NAME

async def search_by_topic_or_subject_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        await update.message.reply_text("Запрос не может быть пустым.")
        return SEARCH_FILE_NAME

    conn = get_db_connection()
    materials = conn.execute(
        '''
        SELECT m.file_name, m.telegram_file_id, t.name as topic_name, s.name as subject_name
        FROM materials m
        JOIN topics t ON m.topic_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        WHERE LOWER(t.name) LIKE LOWER(?) OR LOWER(s.name) LIKE LOWER(?) OR LOWER(m.file_name) LIKE LOWER(?)
        ''',
        (f'%{query}%', f'%{query}%', f'%{query}%')
    ).fetchall()
    conn.close()

    if not materials:
        await update.message.reply_text("Файлы не найдены.")
    else:
        for mat in materials:
            file_name = mat['file_name']
            if file_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                await update.message.reply_photo(photo=mat['telegram_file_id'])
            elif file_name.lower().endswith(('.mp4', '.avi', '.mov')):
                await update.message.reply_video(video=mat['telegram_file_id'])
            else:
                await update.message.reply_document(
                    document=mat['telegram_file_id'],
                    filename=mat['file_name']
                )
            await update.message.reply_text(f"📁 {mat['file_name']}\n📚 Предмет: {mat['subject_name']}\n📝 Тема: {mat['topic_name']}")

    return ConversationHandler.END

# --- Просмотр всех тем в предмете ---
async def view_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_teacher(update.effective_user.id):
        await update.message.reply_text("Только преподаватели могут просматривать темы.")
        return ConversationHandler.END

    conn = get_db_connection()
    subjects = conn.execute('SELECT name FROM subjects').fetchall()
    conn.close()
    if not subjects:
        await update.message.reply_text("Нет доступных предметов.")
        return ConversationHandler.END

    keyboard = [[s['name']] for s in subjects]
    await update.message.reply_text(
        "Выберите предмет для просмотра тем:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return VIEW_TOPICS_SUBJECT

async def view_topics_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject_name = update.message.text.strip()
    conn = get_db_connection()
    subject = conn.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,)).fetchone()
    if not subject:
        await update.message.reply_text("Предмет не найден.")
        await menu(update, context)  # ✅ Возвращаемся к главному меню
        return ConversationHandler.END

    topics = conn.execute('SELECT name FROM topics WHERE subject_id = ?', (subject['id'],)).fetchall()
    conn.close()

    if not topics:
        await update.message.reply_text("В этом предмете нет тем.")
    else:
        topic_list = '\n'.join([f'• {t["name"]}' for t in topics])
        await update.message.reply_text(f"Темы в предмете '{subject_name}':\n{topic_list}")

    await menu(update, context)  # ✅ Возвращаемся к главному меню
    return ConversationHandler.END

# --- Удаление/замена материала ---
async def delete_replace_material(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_teacher(update.effective_user.id):
        await update.message.reply_text("Только преподаватели могут удалять или заменять материалы.")
        return ConversationHandler.END

    keyboard = [['🗑 Удалить материал'], ['🔄 Заменить материал']]
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    # Сохраняем тип действия
    context.user_data['action'] = 'delete' if update.message.text == '🗑 Удалить материал' else 'replace'
    return DELETE_MATERIAL_SELECT_SUBJECT

# Удаление: шаг 1 - выбор предмета
async def delete_material_select_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = 'delete' if 'удалить' in update.message.text.lower() else 'replace'
    context.user_data['action'] = action

    conn = get_db_connection()
    subjects = conn.execute('SELECT name FROM subjects').fetchall()
    conn.close()
    if not subjects:
        await update.message.reply_text("Нет доступных предметов.")
        return ConversationHandler.END

    keyboard = [[s['name']] for s in subjects]
    await update.message.reply_text(
        f"Выберите предмет, чтобы {action} материал:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return DELETE_MATERIAL_SELECT_TOPIC

# Удаление: шаг 2 - выбор темы
async def delete_material_select_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject_name = update.message.text.strip()
    conn = get_db_connection()
    subject = conn.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,)).fetchone()
    if not subject:
        await update.message.reply_text("Предмет не найден.")
        return ConversationHandler.END
    context.user_data['subject_id'] = subject['id']
    topics = conn.execute('SELECT name FROM topics WHERE subject_id = ?', (subject['id'],)).fetchall()
    conn.close()
    if not topics:
        await update.message.reply_text("Нет тем по этому предмету.")
        return ConversationHandler.END
    keyboard = [[t['name']] for t in topics]
    await update.message.reply_text(
        "Выберите тему:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return DELETE_MATERIAL_SELECT_FILE

# Удаление/замена: шаг 3 - выбор файла
async def delete_material_select_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    print(f"[DEBUG] Получен текст: '{text}'")  # 🔍 Отладка

    # Проверяем, это выбор файла (ID: название) или название темы
    if ':' in text and text.split(':')[0].isdigit():
        # Это выбор файла
        file_id = int(text.split(':')[0])
        print(f"[DEBUG] Это выбор файла, ID={file_id}")  # 🔍 Отладка

        action = context.user_data.get('action', 'delete')
        if action == 'replace':
            # --- Замена ---
            await update.message.reply_text("Теперь отправьте новый файл.")
            context.user_data['old_file_id'] = file_id  # ✅ Сохраняем ID файла для замены
            return REPLACE_MATERIAL_NEW_FILE
        else:
            # --- Удаление ---
            conn = get_db_connection()
            try:
                # Удаляем файл
                conn.execute('DELETE FROM materials WHERE id = ?', (file_id,))
                conn.commit()
                await update.message.reply_text("✅ Материал успешно удалён!")

                # Проверяем, остались ли материалы в теме
                topic_id = context.user_data.get('topic_id')
                if topic_id:
                    remaining = conn.execute('SELECT COUNT(*) FROM materials WHERE topic_id = ?', (topic_id,)).fetchone()[0]
                    if remaining == 0:
                        # Удаляем тему, если в ней не осталось материалов
                        conn.execute('DELETE FROM topics WHERE id = ?', (topic_id,))
                        conn.commit()
                        await update.message.reply_text("⚠️ В теме не осталось материалов — тема удалена.")

            except Exception as e:
                logging.error(f"Ошибка при удалении: {e}")
                await update.message.reply_text("❌ Произошла ошибка при удалении файла.")
            finally:
                conn.close()

            await menu(update, context)  # ✅ Возвращаемся к главному меню
            return ConversationHandler.END
    else:
        # Это название темы
        topic_name = text
        subject_id = context.user_data['subject_id']
        print(f"[DEBUG] subject_id={subject_id}, topic_name='{topic_name}'")  # 🔍 Отладка
        conn = get_db_connection()
        # Гибкий поиск темы — без учёта регистра и пробелов
        topic = conn.execute(
            'SELECT id FROM topics WHERE subject_id = ? AND LOWER(name) = LOWER(?)',
            (subject_id, topic_name.strip())
        ).fetchone()
        print(f"[DEBUG] Результат поиска темы: {topic}")  # 🔍 Отладка
        if not topic:
            await update.message.reply_text("❌ Тема не найдена.")
            await menu(update, context)  # ✅ Возвращаемся к главному меню
            return ConversationHandler.END
        context.user_data['topic_id'] = topic['id']
        materials = conn.execute(
            'SELECT id, file_name FROM materials WHERE topic_id = ?',
            (topic['id'],)
        ).fetchall()
        conn.close()
        if not materials:
            await update.message.reply_text("❌ Нет материалов по этой теме.")
            await menu(update, context)  # ✅ Возвращаемся к главному меню
            return ConversationHandler.END

        keyboard = [[str(m['id']) + ': ' + m['file_name']] for m in materials]
        await update.message.reply_text(
            "Выберите файл для удаления:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )
        return DELETE_MATERIAL_SELECT_FILE  # ⚠️ Возвращаемся в то же состояние, чтобы выбрать файл

# Замена: шаг 4 - загрузка нового файла
async def replace_material_new_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Замена: загрузка нового файла (после выбора старого)"""
    logging.debug("[replace_material_new_file] Функция вызвана!")

    # Сначала проверяем фото
    if update.message.photo:
        photo = update.message.photo[-1]
        file_id = photo.file_id
        file_name = f"photo_{photo.file_unique_id}.jpg"
        logging.debug(f"[replace_material_new_file] Получено фото: {file_name}, File ID: {file_id}")

    # Затем видео
    elif update.message.video:
        video = update.message.video
        file_id = video.file_id
        if video.file_name:
            file_name = video.file_name
        else:
            file_name = f"video_{video.file_unique_id}.mp4"
        logging.debug(f"[replace_material_new_file] Получено видео: {file_name}, File ID: {file_id}")

    # Наконец, документ
    elif update.message.document:
        document = update.message.document
        file_name = document.file_name or "material.dat"
        file_id = document.file_id
        mime_type = document.mime_type or ""

        # 📌 Используем оригинальное имя файла, если оно есть
        file_name = document.file_name or f"document_{document.file_unique_id}.dat"

        # 📌 ЛОГИРОВАНИЕ
        logging.debug(f"[replace_material_new_file] Получен документ: {file_name}, MIME type: {mime_type}, File ID: {file_id}")

        allowed_extensions = ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.txt', '.jpg', '.jpeg', '.png', '.mp4', '.avi', '.mov']
        allowed_mimes = [
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'text/plain',
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/webp',
            'video/mp4',
            'video/avi',
            'video/mov',
            'video/wmv',
            'video/flv',
            'video/mpeg',
        ]

        # Проверка формата — только если есть имя файла
        if document.file_name:  # Только если пользователь отправил с именем
            valid_extension = any(file_name.lower().endswith(ext) for ext in allowed_extensions)
            valid_mime = mime_type in allowed_mimes

            if not (valid_extension or valid_mime):
                await update.message.reply_text("❌ Неверный формат файла. Допустимые форматы: PDF, DOC, PPT, TXT, JPG, PNG, MP4 и др.")
                logging.debug("[replace_material_new_file] Неверный формат документа")
                return REPLACE_MATERIAL_NEW_FILE
        # Если имени файла нет — разрешаем (это может быть фото/видео без имени)
    else:
        await update.message.reply_text("Пожалуйста, отправьте файл.")
        return REPLACE_MATERIAL_NEW_FILE

    old_file_id = context.user_data.get('old_file_id')

    if not old_file_id:
        await update.message.reply_text("❌ Не удалось найти файл для замены.")
        await menu(update, context)  # ✅ Возвращаемся к главному меню
        return ConversationHandler.END

    conn = get_db_connection()
    try:
        logging.debug(f"[replace_material_new_file] Попытка замены файла ID={old_file_id} на {file_name}, file_id={file_id}")

        conn.execute(
            'UPDATE materials SET file_name = ?, telegram_file_id = ? WHERE id = ?',
            (file_name, file_id, old_file_id)
        )
        conn.commit()
        await update.message.reply_text("✅ Материал успешно заменён!")
    except Exception as e:
        logging.error(f"Ошибка при замене: {e}")
        await update.message.reply_text("❌ Произошла ошибка при замене файла.")
    finally:
        conn.close()

    await menu(update, context)  # ✅ Возвращаемся к главному меню
    return ConversationHandler.END

# --- Запуск ---
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_ЗДЕСЬ")

    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('add_teacher', add_teacher))

    # Обработчик кнопки "Статистика скачиваний"
    application.add_handler(MessageHandler(filters.Text("📈 Статистика скачиваний"), show_stats))

    # Диалог для поиска материала
    find_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("📚 Найти материал"), find_material)],
        states={
            SELECT_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_subject)],
            SELECT_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_topic)],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # Диалог для загрузки материала
    upload_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("➕ Добавить материал"), add_material)],
        states={
            UPLOAD_SUBJECT: [
                MessageHandler(filters.Text("➕ Новый предмет"), upload_subject),
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_subject)
            ],
            UPLOAD_EXISTING_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_existing_subject)],
            UPLOAD_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_topic)],
            UPLOAD_FILE: [
                MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, upload_file),  # ✅ Обработка файла
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_file_name)  # ✅ Обработка названия файла
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # Диалог для поиска по теме/предмету
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("🔍 Поиск по теме/предмету"), search_by_topic_or_subject)],
        states={
            SEARCH_FILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_topic_or_subject_name)],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # Диалог для просмотра тем
    view_topics_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("📋 Просмотр тем в предмете"), view_topics)],
        states={
            VIEW_TOPICS_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, view_topics_subject)],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # Диалог для удаления/замены
    delete_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("🗑 Удалить/заменить материал"), delete_replace_material)],
        states={
            DELETE_MATERIAL_SELECT_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_material_select_subject)],
            DELETE_MATERIAL_SELECT_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_material_select_topic)],
            DELETE_MATERIAL_SELECT_FILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_material_select_file)],
            REPLACE_MATERIAL_NEW_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, replace_material_new_file)],  # ✅ Добавлено
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # Диалог для замены
    replace_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("🔄 Заменить материал"), delete_replace_material)],
        states={
            DELETE_MATERIAL_SELECT_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_material_select_subject)],
            DELETE_MATERIAL_SELECT_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_material_select_topic)],
            DELETE_MATERIAL_SELECT_FILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_material_select_file)],
            REPLACE_MATERIAL_NEW_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, replace_material_new_file)],  # ✅ Добавлено
        },
        fallbacks=[CommandHandler('start', start)]
    )

    application.add_handler(find_conv)
    application.add_handler(upload_conv)
    application.add_handler(search_conv)
    application.add_handler(view_topics_conv)
    application.add_handler(delete_conv)
    application.add_handler(replace_conv)

    application.run_polling()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()