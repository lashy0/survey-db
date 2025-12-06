TRUNCATE TABLE user_answers, survey_responses, options, questions, survey_tags, tags, surveys, users, countries RESTART IDENTITY CASCADE;

-- Страны
INSERT INTO countries (name) VALUES 
('Россия'), ('Беларусь'), ('Казахстан'), ('Узбекистан'), ('Германия');

-- Пользователи
INSERT INTO users (first_name, last_name, email, password_hash, birth_date, city, country_id, role, registration_date) VALUES 
('Сергей', 'Админов', 'admin@main.com', 'hash1', '1985-05-12', 'Москва', 1, 'admin', NOW() - INTERVAL '1 year'),
('Елена', 'Куратор', 'elena.creator@edu.com', 'hash2', '1992-08-20', 'Санкт-Петербург', 1, 'creator', NOW() - INTERVAL '6 month'),
('Максим', 'Аналитик', 'max.data@tech.com', 'hash3', '1995-03-15', 'Минск', 2, 'creator', NOW() - INTERVAL '5 month'),
('Анна', 'Смирнова', 'anna2003@mail.ru', 'hash4', '2003-07-01', 'Москва', 1, 'user', NOW() - INTERVAL '1 month'),
('Дмитрий', 'Волков', 'dimon_v@bk.ru', 'hash5', '2005-11-10', 'Казань', 1, 'user', NOW() - INTERVAL '3 weeks'),
('Ольга', 'Иванова', 'olga80@list.ru', 'hash6', '1980-02-28', 'Новосибирск', 1, 'user', NOW() - INTERVAL '2 month'),
('Иван', 'Казах', 'ivan.kz@mail.kz', 'hash7', '1998-09-15', 'Алматы', 3, 'user', NOW() - INTERVAL '10 days'),
('Мария', 'Берлин', 'mary.de@gmail.com', 'hash8', '1990-06-05', 'Берлин', 5, 'user', NOW() - INTERVAL '1 year'),
('Павел', 'Геймер', 'pasha_game@yandex.ru', 'hash9', '2007-01-20', 'Екатеринбург', 1, 'user', NOW() - INTERVAL '5 days'),
('Светлана', 'Врач', 'svetlana.med@mail.ru', 'hash10', '1975-12-12', 'Минск', 2, 'user', NOW() - INTERVAL '4 month'),
('Артем', 'Студент', 'artem.student@edu.ru', 'hash11', '2004-04-04', 'Москва', 1, 'user', NOW() - INTERVAL '2 days'),
('Виктория', 'Бизнес', 'vika.biz@corp.com', 'hash12', '1988-08-08', 'Астана', 3, 'user', NOW() - INTERVAL '3 month');

-- Теги
INSERT INTO tags (name) VALUES 
('IT'), ('Здоровье'), ('Гейминг'), ('Образование'), ('Работа'), ('Психология');

-- Опросы

-- Опрос 1: IT Предпочтения (Активный)
INSERT INTO surveys (title, description, status, author_id, start_date, end_date) VALUES 
('Технологии 2025', 'Какие языки программирования вы выбираете?', 'active', 2, NOW() - INTERVAL '10 days', NOW() + INTERVAL '20 days');

-- Опрос 2: Здоровье и Удаленка (Завершенный)
INSERT INTO surveys (title, description, status, author_id, start_date, end_date) VALUES 
('Влияние удаленной работы на здоровье', 'Анонимный опрос для сотрудников', 'completed', 3, NOW() - INTERVAL '2 month', NOW() - INTERVAL '1 month');

-- Опрос 3: Ожидания от игр (Черновик)
INSERT INTO surveys (title, description, status, author_id) VALUES 
('Игровая индустрия: ожидания', 'Исследование спроса на новые жанры', 'draft', 2);

-- Связь Опросы-Теги
INSERT INTO survey_tags (survey_id, tag_id) VALUES 
(1, 1), (1, 4), -- Опрос 1: IT, Образование
(2, 2), (2, 5), (2, 6), -- Опрос 2: Здоровье, Работа, Психология
(3, 1), (3, 3); -- Опрос 3: IT, Гейминг

-- Вопросы и Варианты

-- Для Опроса 1
INSERT INTO questions (survey_id, question_text, question_type, position, is_required) VALUES 
(1, 'Ваш основной язык программирования?', 'single_choice', 1, TRUE),
(1, 'Ваш опыт работы (лет)?', 'single_choice', 2, TRUE),
(1, 'Какие IDE вы используете?', 'multiple_choice', 3, FALSE);

INSERT INTO options (question_id, option_text) VALUES 
(1, 'Python'), (1, 'Java'), (1, 'JavaScript'), (1, 'C++'), (1, 'Go'),
(2, '0-1 год'), (2, '1-3 года'), (2, '3-5 лет'), (2, 'Более 5 лет'),
(3, 'VS Code'), (3, 'IntelliJ IDEA'), (3, 'PyCharm'), (3, 'Vim');

-- Для Опроса 2
INSERT INTO questions (survey_id, question_text, question_type, position, is_required) VALUES 
(2, 'Как часто вы делаете перерывы?', 'single_choice', 1, TRUE),
(2, 'Оцените уровень стресса (1-5)', 'rating', 2, TRUE),
(2, 'Что помогает вам расслабиться?', 'text_answer', 3, FALSE);

INSERT INTO options (question_id, option_text) VALUES 
(4, 'Каждый час'), (4, 'Раз в 3-4 часа'), (4, 'Не делаю перерывов'),
(5, '1'), (5, '2'), (5, '3'), (5, '4'), (5, '5');


-- Ответы пользователей

INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type) 
VALUES (1, 4, NOW() - INTERVAL '50 hours', NOW() - INTERVAL '49 hours 57 minutes', '192.168.0.101', 'Mobile');
INSERT INTO user_answers (response_id, question_id, selected_option_id) VALUES (1, 1, 1), (1, 2, 6); 

INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type) 
VALUES (1, 5, NOW() - INTERVAL '30 hours', NOW() - INTERVAL '29 hours 45 minutes', '10.0.0.55', 'Desktop');
INSERT INTO user_answers (response_id, question_id, selected_option_id) VALUES (2, 1, 3), (2, 2, 7);

INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type) 
VALUES (1, 11, NOW() - INTERVAL '5 hours', NOW() - INTERVAL '4 hours 55 minutes', '172.16.0.1', 'Mobile');
INSERT INTO user_answers (response_id, question_id, selected_option_id) VALUES (3, 1, 1), (3, 2, 6);

INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type) 
VALUES (2, 6, '2025-09-10 09:00:00', '2025-09-10 09:20:00', '95.100.200.1', 'Desktop');
INSERT INTO user_answers (response_id, question_id, selected_option_id) VALUES (4, 4, 14), (4, 5, 18);
INSERT INTO user_answers (response_id, question_id, text_answer) VALUES (4, 6, 'Прогулки с собакой');

INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type) 
VALUES (2, 10, '2025-09-12 18:00:00', '2025-09-12 18:10:00', '37.29.10.5', 'Tablet');
INSERT INTO user_answers (response_id, question_id, selected_option_id) VALUES (5, 4, 13), (5, 5, 17);

INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address, device_type) 
VALUES (2, 12, '2025-09-15 12:00:00', '2025-09-15 12:05:00', '88.10.20.30', 'Desktop');
INSERT INTO user_answers (response_id, question_id, selected_option_id) VALUES (6, 4, 13), (6, 5, 19);