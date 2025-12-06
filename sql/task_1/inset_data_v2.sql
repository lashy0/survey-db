-- 1. Очистка старых данных
TRUNCATE TABLE user_answers, survey_responses, options, questions, survey_tags, tags, surveys, users, countries RESTART IDENTITY CASCADE;

-- 2. Базовые справочники
INSERT INTO countries (name) VALUES 
('Россия'), ('Беларусь'), ('Казахстан'), ('Узбекистан'), ('Германия'), ('США');

INSERT INTO tags (name) VALUES 
('IT'), ('Здоровье'), ('Гейминг'), ('Образование'), ('Работа'), ('Психология');

-- 3. Пользователи
INSERT INTO users (first_name, last_name, email, password_hash, birth_date, city, country_id, role, registration_date) VALUES 
('Сергей', 'Админов', 'admin@main.com', 'hash1', '1985-05-12', 'Москва', 1, 'admin', '2023-01-01'),
('Елена', 'Куратор', 'elena.creator@edu.com', 'hash2', '1992-08-20', 'Санкт-Петербург', 1, 'creator', '2023-05-01'),
('Максим', 'Аналитик', 'max.data@tech.com', 'hash3', '1995-03-15', 'Минск', 2, 'creator', '2023-06-01'),
('Анна', 'Смирнова', 'anna2003@mail.ru', 'hash4', '2003-07-01', 'Москва', 1, 'user', '2024-01-10'),
('Дмитрий', 'Волков', 'dimon_v@bk.ru', 'hash5', '2005-11-10', 'Казань', 1, 'user', '2024-02-15'),
('Ольга', 'Иванова', 'olga80@list.ru', 'hash6', '1980-02-28', 'Новосибирск', 1, 'user', '2024-03-01'),
('Иван', 'Казах', 'ivan.kz@mail.kz', 'hash7', '1998-09-15', 'Алматы', 3, 'user', '2024-04-05'),
('Мария', 'Берлин', 'mary.de@gmail.com', 'hash8', '1990-06-05', 'Берлин', 5, 'user', '2023-10-10'),
('Павел', 'Геймер', 'pasha_game@yandex.ru', 'hash9', '2007-01-20', 'Екатеринбург', 1, 'user', '2025-01-01'),
('Светлана', 'Врач', 'svetlana.med@mail.ru', 'hash10', '1975-12-12', 'Минск', 2, 'user', '2024-08-12'),
('Артем', 'Студент', 'artem.student@edu.ru', 'hash11', '2004-04-04', 'Москва', 1, 'user', '2025-09-01'),
('Виктория', 'Бизнес', 'vika.biz@corp.com', 'hash12', '1988-08-08', 'Астана', 3, 'user', '2024-11-01');

-- Генерация массовки
INSERT INTO users (first_name, last_name, email, password_hash, birth_date, city, country_id, role, registration_date)
SELECT 
    'User' || i, 
    'Testov' || i, 
    'user' || i || '@test.com', 
    'hash_gen', 
    '1990-01-01'::date + (random() * 365 * 10)::integer, 
    CASE WHEN i % 2 = 0 THEN 'Москва' ELSE 'Минск' END,
    CASE WHEN i % 2 = 0 THEN 1 ELSE 2 END,
    'user',
    '2024-01-01'::date + (random() * 600)::integer 
FROM generate_series(13, 100) AS i; -- Увеличим до 100 пользователей, чтобы меньше было коллизий


-- 4. Опросы
INSERT INTO surveys (title, description, status, author_id, start_date, end_date) VALUES 
('Технологии 2024', 'Опрос прошлого года', 'completed', 2, '2024-01-01', '2024-12-31'),
('Технологии 2025', 'Опрос этого года', 'active', 2, '2025-01-01', '2025-12-31'),
('Удаленка и здоровье', 'Влияние работы из дома', 'active', 3, '2024-06-01', '2025-06-01');

INSERT INTO survey_tags (survey_id, tag_id) VALUES (1, 1), (2, 1), (3, 2), (3, 5);


-- 5. Вопросы
INSERT INTO questions (survey_id, question_text, question_type, position, is_required) VALUES 
(1, 'Ваш язык программирования?', 'single_choice', 1, TRUE), 
(2, 'Ваш язык программирования?', 'single_choice', 1, TRUE),
(3, 'Уровень стресса?', 'rating', 1, TRUE);

INSERT INTO options (question_id, option_text) VALUES 
(1, 'Python'), (1, 'Java'), (1, 'Go'),
(2, 'Python'), (2, 'Java'), (2, 'Rust'),
(3, '1'), (3, '5');


-- 6. ГЕНЕРАЦИЯ ОТВЕТОВ (С ЗАЩИТОЙ ОТ ДУБЛЕЙ)

-- 6.1. Ответы за 2024 год
INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type)
SELECT 
    1, 
    (random() * 99 + 1)::int, -- random user 1-100
    ts, 
    ts + interval '10 minutes',
    '192.168.0.1',
    CASE WHEN random() > 0.5 THEN 'Mobile' ELSE 'Desktop' END
FROM (
    SELECT '2024-01-01'::timestamp + (random() * (365 * 24 * 3600)) * '1 second'::interval as ts
    FROM generate_series(1, 150) -- Пытаемся вставить 150 записей
) t
ON CONFLICT DO NOTHING; -- Игнорируем дубликаты

-- 6.2. Ответы за 2025 год
INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type)
SELECT 
    2, 
    (random() * 99 + 1)::int,
    ts, 
    ts + interval '5 minutes',
    '10.0.0.1',
    CASE WHEN random() > 0.5 THEN 'Mobile' ELSE 'Desktop' END
FROM (
    SELECT '2025-01-01'::timestamp + (random() * (300 * 24 * 3600)) * '1 second'::interval as ts
    FROM generate_series(1, 200)
) t
ON CONFLICT DO NOTHING;

-- 6.3. Сентябрь 2025
INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type)
SELECT 
    3, 
    (random() * 99 + 1)::int,
    ts, 
    ts + interval '15 minutes',
    '88.0.0.1',
    'Mobile'
FROM (
    SELECT '2025-09-01'::timestamp + (random() * (30 * 24 * 3600)) * '1 second'::interval as ts
    FROM generate_series(1, 50)
) t
ON CONFLICT DO NOTHING;

-- 6.4. Октябрь 2025
INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type)
SELECT 
    3, 
    (random() * 99 + 1)::int,
    ts, 
    ts + interval '15 minutes',
    '88.0.0.1',
    'Mobile'
FROM (
    SELECT '2025-10-01'::timestamp + (random() * (30 * 24 * 3600)) * '1 second'::interval as ts
    FROM generate_series(1, 15)
) t
ON CONFLICT DO NOTHING;

-- Заполнение ответов (только для существующих сессий)
INSERT INTO user_answers (response_id, question_id, selected_option_id)
SELECT response_id, 1, 1 FROM survey_responses WHERE survey_id = 1;

INSERT INTO user_answers (response_id, question_id, selected_option_id)
SELECT response_id, 2, 4 FROM survey_responses WHERE survey_id = 2;