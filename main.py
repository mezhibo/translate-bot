from __future__ import annotations

import logging
from typing import Dict, Any, Tuple, Optional

import telebot
from telebot import types

from config import load_config
from db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("englishcard")

# ---------------- Inline callbacks ----------------
CB_PICK = "pick"   # pick:<idx>
CB_NEXT = "next"
CB_ADD = "add"
CB_DEL = "del"

# ---------------- In-memory session storage ----------------
# Текущая карточка для пользователя
quiz_state: Dict[Tuple[int, int], Dict[str, Any]] = {}   # (chat_id, tg_user_id) -> {word_id, en, correct_ru, options_ru}

# Режим добавления слова
add_state: Dict[Tuple[int, int], Dict[str, Any]] = {}    # (chat_id, tg_user_id) -> {step: "en"/"ru", en: str}

def _key(chat_id: int, user_id: int) -> Tuple[int, int]:
    return (chat_id, user_id)

def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().replace("ё", "е").split())

def build_inline_kb(options_ru: list[str]) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)

    # варианты ответов
    btns = []
    for i, opt in enumerate(options_ru):
        btns.append(types.InlineKeyboardButton(text=opt, callback_data=f"{CB_PICK}:{i}"))
    kb.add(*btns)

    # управление
    kb.add(
        types.InlineKeyboardButton("Дальше ⏭", callback_data=CB_NEXT),
        types.InlineKeyboardButton("Добавить слово ➕", callback_data=CB_ADD),
        types.InlineKeyboardButton("Удалить слово 🗑", callback_data=CB_DEL),
    )
    return kb

def remove_reply_keyboard(bot: telebot.TeleBot, chat_id: int):
    # Telegram не принимает пустой текст => шлём нормальный символ
    bot.send_message(chat_id, "Клавиатуру убрал ✅", reply_markup=types.ReplyKeyboardRemove())

def show_card(bot: telebot.TeleBot, db: Database, chat_id: int, tg_user_id: int):
    user_id = db.ensure_user(tg_user_id)
    word, options = db.pick_quiz(user_id=user_id)

    quiz_state[_key(chat_id, tg_user_id)] = {
        "word_id": word.id,
        "en": word.en,
        "correct_ru": word.ru,
        "options_ru": options,
    }

    kb = build_inline_kb(options)
    bot.send_message(
        chat_id,
        f"Как переводится: <b>{word.en}</b> ?",
        reply_markup=kb,
        parse_mode="HTML",
    )

def main():
    cfg = load_config()
    db = Database(cfg.database_url)

    bot = telebot.TeleBot(cfg.bot_token)

    # сброс webhook — чтобы polling работал стабильно
    try:
        bot.remove_webhook()
    except Exception:
        pass

    try:
        me = bot.get_me()
        log.info("Running as @%s (id=%s)", me.username, me.id)
    except Exception:
        log.info("Running bot (get_me failed)")

    @bot.message_handler(commands=["start"])
    def start_handler(message: types.Message):
        log.info("START from telegram_id=%s chat_id=%s", message.from_user.id, message.chat.id)
        db.ensure_user(message.from_user.id)

        # убрать старую ReplyKeyboard, если осталась снизу
        remove_reply_keyboard(bot, message.chat.id)

        bot.send_message(
            message.chat.id,
            "Привет! Я EnglishCard 🤖\n\n"
            "Команды:\n"
            "• /cards — показать карточку\n\n"
            "Отвечай кнопками под карточкой 👇"
        )

    @bot.message_handler(commands=["cards"])
    def cards_handler(message: types.Message):
        remove_reply_keyboard(bot, message.chat.id)
        show_card(bot, db, message.chat.id, message.from_user.id)

    # ---------- text handler (для add word + на всякий случай ответы текстом) ----------
    @bot.message_handler(content_types=["text"])
    def text_handler(message: types.Message):
        chat_id = message.chat.id
        tg_user_id = message.from_user.id
        k = _key(chat_id, tg_user_id)
        txt = (message.text or "").strip()

        # 1) режим добавления слова
        st = add_state.get(k)
        if st:
            if st["step"] == "en":
                en = txt
                if not en or len(en) > 50:
                    bot.send_message(chat_id, "Введите ENG-слово (1–50 символов).")
                    return
                add_state[k] = {"step": "ru", "en": en}
                bot.send_message(chat_id, f"Ок. Теперь введи перевод для “{en}” на русском")
                return

            if st["step"] == "ru":
                ru = txt
                en = st.get("en", "")
                if not ru or len(ru) > 80:
                    bot.send_message(chat_id, "Введите перевод (1–80 символов).")
                    return
                user_id = db.ensure_user(tg_user_id)
                try:
                    db.add_personal_word(user_id=user_id, en=en, ru=ru)
                except Exception as e:
                    log.exception("add_personal_word failed")
                    bot.send_message(chat_id, f"Не смог сохранить слово 😬\nПричина: {e}")
                    add_state.pop(k, None)
                    return

                add_state.pop(k, None)
                bot.send_message(chat_id, f"Сохранил ✅ {en} — {ru}\nЖми /cards")
                return

        # 2) если это ответ текстом (например, прилетело от старой клавы)
        q = quiz_state.get(k)
        if q and q.get("correct_ru"):
            correct_ru = q["correct_ru"]
            options_ru = q.get("options_ru", [])
            if _norm(txt) == _norm(correct_ru):
                bot.send_message(chat_id, "✅ Верно! Жми “Дальше ⏭”.")
                return
            if _norm(txt) in {_norm(x) for x in options_ru}:
                bot.send_message(chat_id, f"❌ Неверно. Правильно: {correct_ru}")
                return

        # иначе игнор/подсказка
        if txt not in ("/start", "/cards"):
            bot.send_message(chat_id, "Нажми /cards 🙂")

    # ---------- inline callbacks ----------
    @bot.callback_query_handler(func=lambda call: True)
    def callbacks(call: types.CallbackQuery):
        try:
            chat_id = call.message.chat.id
            tg_user_id = call.from_user.id
            k = _key(chat_id, tg_user_id)

            data = call.data or ""
            log.info("CALLBACK %s from user=%s chat=%s", data, tg_user_id, chat_id)

            # если пользователь сейчас добавляет слово — просим закончить
            if k in add_state:
                bot.answer_callback_query(call.id, "Сначала закончи добавление слова 🙂", show_alert=False)
                return

            if data == CB_NEXT:
                bot.answer_callback_query(call.id)
                show_card(bot, db, chat_id, tg_user_id)
                return

            if data == CB_ADD:
                bot.answer_callback_query(call.id)
                add_state[k] = {"step": "en"}
                bot.send_message(chat_id, "Ок! Введи слово на английском (например: apple)")
                return

            if data == CB_DEL:
                bot.answer_callback_query(call.id)
                q = quiz_state.get(k)
                if not q:
                    bot.send_message(chat_id, "Сначала нажми /cards, потом “Удалить слово”.")
                    return

                current_word_id = q.get("word_id")
                current_en = q.get("en")
                user_id = db.ensure_user(tg_user_id)

                try:
                    owner = db.get_word_owner(int(current_word_id))
                    if owner is None:
                        db.hide_word_for_user(user_id, int(current_word_id))
                        bot.send_message(chat_id, f"Спрятал слово “{current_en}” только для тебя 🫥")
                    elif owner == user_id:
                        deleted = db.delete_personal_word(user_id, int(current_word_id))
                        bot.send_message(chat_id, f"Удалил твоё слово “{current_en}” 🗑" if deleted else "Не получилось удалить.")
                    else:
                        db.hide_word_for_user(user_id, int(current_word_id))
                        bot.send_message(chat_id, f"Спрятал слово “{current_en}” только для тебя 🫥")
                except Exception as e:
                    log.exception("delete/hide failed")
                    bot.send_message(chat_id, f"Ошибка при удалении/скрытии 😬\n{e}")
                return

            if data.startswith(f"{CB_PICK}:"):
                q = quiz_state.get(k)
                if not q:
                    bot.answer_callback_query(call.id, "Нажми /cards ещё раз 🙂")
                    return

                try:
                    idx = int(data.split(":")[1])
                except Exception:
                    bot.answer_callback_query(call.id, "Ошибка кнопки 😬")
                    return

                options = q.get("options_ru", [])
                correct_ru = q.get("correct_ru")

                if not options or correct_ru is None or idx < 0 or idx >= len(options):
                    bot.answer_callback_query(call.id, "Нажми /cards ещё раз 🙂")
                    return

                chosen = options[idx]
                if _norm(chosen) == _norm(correct_ru):
                    bot.answer_callback_query(call.id, "✅ Верно!")
                    bot.send_message(chat_id, "✅ Верно! Жми “Дальше ⏭”.")
                else:
                    bot.answer_callback_query(call.id, "❌ Неверно")
                    bot.send_message(chat_id, f"❌ Неверно. Правильно: {correct_ru}\nЖми “Дальше ⏭” или попробуй ещё.")
                return

            bot.answer_callback_query(call.id)
        except Exception:
            # чтобы polling не умирал при любой мелочи
            log.exception("callback handler crashed")
            try:
                bot.answer_callback_query(call.id, "Ошибка 😬")
            except Exception:
                pass

    log.info("Bot started.")
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    main()
