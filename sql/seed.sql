BEGIN;

-- 12+ общих слов (можешь расширять)
INSERT INTO words (en, ru, owner_user_id) VALUES
('red', 'красный', NULL),
('blue', 'синий', NULL),
('green', 'зелёный', NULL),
('yellow', 'жёлтый', NULL),
('black', 'чёрный', NULL),
('white', 'белый', NULL),
('orange', 'оранжевый', NULL),
('purple', 'фиолетовый', NULL),
('pink', 'розовый', NULL),
('brown', 'коричневый', NULL),
('gray', 'серый', NULL),
('hello', 'привет', NULL)
ON CONFLICT DO NOTHING;

COMMIT;
