from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, List, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass
class Word:
    id: int
    en: str
    ru: str
    owner_user_id: Optional[int]


class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)

    # ---------- users ----------
    def ensure_user(self, telegram_id: int) -> int:
        """Создаёт user если нет, возвращает внутренний users.id"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (telegram_id)
                    VALUES (%s)
                    ON CONFLICT (telegram_id) DO UPDATE SET telegram_id = EXCLUDED.telegram_id
                    RETURNING id;
                    """,
                    (telegram_id,),
                )
                user_id = cur.fetchone()[0]
                return user_id

    # ---------- words ----------
    def add_personal_word(self, user_id: int, en: str, ru: str) -> Word:
        en = en.strip()
        ru = ru.strip()
        if not en or not ru:
            raise ValueError("Пустое слово/перевод")

        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO words (en, ru, owner_user_id)
                    VALUES (%s, %s, %s)
                    RETURNING id, en, ru, owner_user_id;
                    """,
                    (en, ru, user_id),
                )
                row = cur.fetchone()
                return Word(**row)

    def hide_word_for_user(self, user_id: int, word_id: int) -> None:
        """Прячет слово для пользователя (актуально для общих слов)."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO hidden_words (user_id, word_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, word_id) DO NOTHING;
                    """,
                    (user_id, word_id),
                )

    def delete_personal_word(self, user_id: int, word_id: int) -> bool:
        """Удаляет персональное слово (только если владелец user_id). Возвращает True если удалено."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM words
                    WHERE id = %s AND owner_user_id = %s;
                    """,
                    (word_id, user_id),
                )
                return cur.rowcount > 0

    def get_available_words_for_user(self, user_id: int) -> List[Word]:
        """Все доступные слова: общие + персональные, исключая скрытые для user."""
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT w.id, w.en, w.ru, w.owner_user_id
                    FROM words w
                    WHERE
                        (
                            w.owner_user_id IS NULL
                            OR w.owner_user_id = %s
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM hidden_words hw
                            WHERE hw.user_id = %s AND hw.word_id = w.id
                        )
                    ORDER BY w.id;
                    """,
                    (user_id, user_id),
                )
                rows = cur.fetchall()
                return [Word(**r) for r in rows]

    def pick_quiz(self, user_id: int) -> Tuple[Word, List[str]]:
        """
        Возвращает:
        - выбранное слово (Word)
        - список из 4 вариантов перевода (ru), перемешанный
        """
        words = self.get_available_words_for_user(user_id)
        if len(words) < 4:
            raise RuntimeError(
                "Недостаточно слов для викторины (нужно минимум 4). "
                "Добавь слова или сбрось скрытые."
            )

        correct = random.choice(words)
        others = [w for w in words if w.id != correct.id]
        wrong = random.sample(others, 3)

        options = [correct.ru] + [w.ru for w in wrong]
        random.shuffle(options)
        return correct, options

    def is_word_personal(self, word_id: int) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT owner_user_id IS NOT NULL FROM words WHERE id = %s;", (word_id,))
                row = cur.fetchone()
                return bool(row and row[0])

    def get_word_owner(self, word_id: int) -> Optional[int]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT owner_user_id FROM words WHERE id = %s;", (word_id,))
                row = cur.fetchone()
                return row[0] if row else None
