-- 1. Запросы с множественными операциями (объединение, пересечение, разность)

-- Найти всех уникальных людей, которые либо создавали опросы, 
-- либо проходили их. (Список всех активных участников платформы)
-- Демонстрация: UNION (объединяет результаты и убирает дубликаты)
SELECT author_id AS id_person FROM surveys 
UNION
SELECT user_id FROM survey_responses;

-- Найти ID опросов, которые активны (status='active') 
-- И одновременно имеют хотя бы одно прохождение.
-- Демонстрация: INTERSECT (возвращает только общие значения)
SELECT survey_id FROM surveys WHERE status = 'active'
INTERSECT
SELECT survey_id FROM survey_responses;

-- Найти ID опросов, которые были созданы, 
-- но НИКТО их еще не проходил (пустые опросы).
-- Демонстрация: EXCEPT (вычитает из первого набора второй)
SELECT survey_id FROM surveys
EXCEPT
SELECT survey_id FROM survey_responses;


-- 2. Многотабличные запросы

-- Вывести имя пользователя и название его страны (вместо ID страны)
-- Демонстрация: INNER JOIN (соединение двух таблиц)
SELECT 
    u.first_name, 
    u.last_name, 
    c.name AS country_name
FROM users u
JOIN countries c ON u.country_id = c.country_id;

-- Вывести название опроса и имя его автора
-- Демонстрация: LEFT JOIN (покажет опрос, даже если автор был удален и стал NULL)
SELECT 
    s.title AS survey_title, 
    CONCAT(u.first_name, ' ', u.last_name) AS author_name
FROM surveys s
LEFT JOIN users u ON s.author_id = u.user_id;

-- Показать текст вопроса и к какому опросу он относится
-- Демонстрация: JOIN (связь 1-ко-многим)
SELECT 
    s.title, 
    q.question_text, 
    q.question_type
FROM questions q
JOIN surveys s ON q.survey_id = s.survey_id
ORDER BY s.title, q.position;

-- Вывести название опроса и список его тегов через запятую
-- Демонстрация: JOIN трех таблиц (surveys -> survey_tags -> tags) + STRING_AGG
SELECT 
    s.title,
    STRING_AGG(t.name, ', ') AS tags_list
FROM surveys s
JOIN survey_tags st ON s.survey_id = st.survey_id
JOIN tags t ON st.tag_id = t.tag_id
GROUP BY s.survey_id, s.title;


-- 3. Многотабличные  запросы с агрегатными функциями, с группировкой данных, с условием для отбора групп

-- Аналитика по странам: Сколько пользователей из каждой страны?
-- Выводим название страны и число пользователей.
SELECT 
    c.name AS country, 
    COUNT(u.user_id) AS total_users
FROM countries c
LEFT JOIN users u ON c.country_id = u.country_id
GROUP BY c.name
ORDER BY total_users DESC;

-- Аналитика популярности: Топ опросов по количеству прохождений
-- Выводим название опроса и сколько раз его прошли.
SELECT 
    s.title, 
    COUNT(r.response_id) AS responses_count
FROM surveys s
LEFT JOIN survey_responses r ON s.survey_id = r.survey_id
GROUP BY s.survey_id, s.title
HAVING COUNT(r.response_id) > 0
ORDER BY responses_count DESC;

-- Средний возраст респондентов для каждого опроса
-- Соединяем Опросы -> Ответы -> Пользователи -> Считаем средний возраст
SELECT 
    s.title,
    ROUND(AVG(EXTRACT(YEAR FROM AGE(u.birth_date))), 1) AS avg_respondent_age
FROM surveys s
JOIN survey_responses r ON s.survey_id = r.survey_id
JOIN users u ON r.user_id = u.user_id
GROUP BY s.survey_id, s.title;