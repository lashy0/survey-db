-- 1. Работа с неструктурированнымими данными 

-- Создаем индекс для полнотекстового поиска по описанию опросов
-- Используем функцию to_tsvector для русского языка
CREATE INDEX idx_surveys_description_gin 
ON surveys USING GIN (to_tsvector('russian', description));

-- Пример запроса: Найти опросы, где в описании встречаются слова "студент" или "обучение"
-- Оператор @@ проверяет совпадение с вектором
SELECT title, description 
FROM surveys 
WHERE to_tsvector('russian', description) @@ to_tsquery('russian', 'опрос | обучение');


-- 2. Запросы на регулярные выражения
-- В PostgreSQL для этого используется оператор ~ (case-sensitive) или ~* (case-insensitive)

-- Найти пользователей, у которых email принадлежит корпоративным доменам 
-- (например, .com, .org, .net), но не .ru
-- Регулярка: @.*\.(com|org|net)$
SELECT email 
FROM users 
WHERE email ~* '@.*\.(com|org|net)$';

-- Найти вопросы, которые начинаются с "Как" или "Что" (проверка формулировок)
SELECT question_text 
FROM questions 
WHERE question_text ~* '^(Как|Что).*';


-- 3. Hint (pg_hint_plan)
-- установлено расширение pg_hint_plan, можем использовать
-- специальные комментарии /*+ ... */ для управления планировщиком.

-- Включаем расширение (нужно сделать один раз)
--CREATE EXTENSION IF NOT EXISTS pg_hint_plan;

SET enable_seqscan = ON;
SET enable_indexscan = ON;

-- Заставляем базу использовать Index Scan
-- Даже если таблица маленькая и Postgres хочет сделать SeqScan, мы его заставим читать индекс.
-- Хинт: /*+ IndexScan(users) */
/*+ IndexScan(users) */
EXPLAIN ANALYZE
SELECT * FROM users WHERE email = 'alex@example.com';

-- Запрещаем Index Scan (заставляем читать всю таблицу)
-- Хинт: /*+ SeqScan(users) */
/*+ SeqScan(users) */
EXPLAIN ANALYZE
SELECT * FROM users WHERE email = 'alex@example.com';


-- 4. Партиционирование
-- Демонстрация на примере таблицы логов (так как существующие таблицы сложно переделать на лету).
-- Создадим таблицу "Журнал действий", которая разбита на части по годам.

-- Создаем мастер-таблицу с партиционированием по диапазону (RANGE)
CREATE TABLE audit_logs (
    log_id SERIAL,
    event_time TIMESTAMPTZ NOT NULL,
    user_id INTEGER,
    action TEXT
) PARTITION BY RANGE (event_time);

-- Создаем партиции (секции) для конкретных периодов
-- Данные за 2024 год
CREATE TABLE audit_logs_2024 PARTITION OF audit_logs
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

-- Данные за 2025 год
CREATE TABLE audit_logs_2025 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

-- Вставка данных (Postgres сам направит их в нужную подтаблицу)
INSERT INTO audit_logs (event_time, user_id, action) VALUES 
('2024-12-31 23:59:00', 1, 'Login'), -- Попадет в audit_logs_2024
('2025-01-01 00:01:00', 1, 'Create Survey'); -- Попадет в audit_logs_2025

-- Проверка: читаем из главной таблицы, а данные берутся из секций
SELECT tableoid::regclass AS partition_name, * FROM audit_logs;