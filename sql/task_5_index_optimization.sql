-- 1. Работа с неструктурированнымими данными

-- индекс для быстрого поиска по описанию опроса
CREATE INDEX idx_surveys_description_gin 
ON surveys USING GIN (to_tsvector('russian', description));

-- 2. Запросы на регулярные выражения

-- поиска email, который не содержит популярные домены
SELECT full_name, email 
FROM users 
WHERE email !~* '@(gmail|yandex|mail|bk|list)\.(com|ru)$';

-- поиск вопросов, которые начинаются как/что/почему
SELECT question_text 
FROM questions 
WHERE question_text ~* '^(Как|Почему|Что).*';

-- 3. Hint


-- 4. Партиционирование

-- новая таблица
CREATE TABLE audit_logs (
    log_id SERIAL,
    event_time TIMESTAMPTZ NOT NULL,
    user_id INTEGER,
    action TEXT
) PARTITION BY RANGE (event_time);

-- создание секций под конкретные года (2024 и 2025)
CREATE TABLE audit_logs_2024 PARTITION OF audit_logs
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE audit_logs_2025 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

-- создаем данные
INSERT INTO audit_logs (event_time, user_id, action) VALUES 
('2024-05-15 10:00:00', 1, 'Регистрация'),
('2024-12-31 23:59:00', 2, 'Прохождение опроса'),
('2025-01-01 00:01:00', 1, 'Создание опроса');

SELECT * FROM audit_logs;

SELECT * FROM audit_logs_2024;