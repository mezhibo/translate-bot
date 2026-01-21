BEGIN;

-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    telegram_id     BIGINT UNIQUE NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Слова (общие и персональные)
-- owner_user_id = NULL -> слово общее
-- owner_user_id = users.id -> слово персональное конкретного пользователя
CREATE TABLE IF NOT EXISTS words (
    id              BIGSERIAL PRIMARY KEY,
    en              TEXT NOT NULL,
    ru              TEXT NOT NULL,
    owner_user_id   BIGINT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Чтобы в рамках одного владельца не было дублей по en
-- (у общих owner_user_id NULL: PostgreSQL позволяет много NULL, поэтому добавим частичный индекс ниже)
CREATE UNIQUE INDEX IF NOT EXISTS uq_words_owner_en
ON words (owner_user_id, lower(en));

-- Уникальность для общих слов (owner_user_id IS NULL)
CREATE UNIQUE INDEX IF NOT EXISTS uq_words_global_en
ON words (lower(en))
WHERE owner_user_id IS NULL;

-- Скрытые слова для конкретного пользователя (удаление "только для меня" для общих слов)
CREATE TABLE IF NOT EXISTS hidden_words (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id     BIGINT NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    hidden_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, word_id)
);

COMMIT;
