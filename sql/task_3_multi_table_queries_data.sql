-- 1. Запросы с множественными операциями

-- объединение
-- получить список ID всех людей, которые проявили активность
SELECT author_id AS user_id FROM surveys 
WHERE author_id IS NOT NULL
UNION
SELECT user_id FROM survey_responses
WHERE user_id IS NOT NULL;

-- пересечение
-- найти опросы, которые активные и при этом их уже кто-то проходил
SELECT survey_id FROM surveys WHERE status = 'active'
INTERSECT
SELECT survey_id FROM survey_responses;

-- разность
-- найти опросы, которые созданы, но никто их еще не проходил
SELECT survey_id FROM surveys
EXCEPT
SELECT survey_id FROM survey_responses;

-- 2. Многотабличные запросы

-- вывести имя пользователя и название его страны
SELECT 
    u.full_name, 
    c.name AS country_name,
    u.city
FROM users u
JOIN countries c ON u.country_id = c.country_id
ORDER BY c.name;

-- показать заголовок опроса и имя автора
SELECT 
    s.title AS survey_title, 
    u.full_name AS author_name,
    s.created_at
FROM surveys s
LEFT JOIN users u ON s.author_id = u.user_id;

-- вывести название опросов и теги, которые к ним привязаны
SELECT 
    s.title AS survey_title,
    t.name AS tag_name
FROM surveys s
JOIN survey_tags st ON s.survey_id = st.survey_id
JOIN tags t ON st.tag_id = t.tag_id;

-- 3. Многотабличные  запросы с агрегатными функциями, с группировкой данных, с условием для отбора групп

-- сколько пользователей зарегистировано в каждой стране
SELECT 
    c.name AS country, 
    COUNT(u.user_id) AS total_users
FROM countries c
LEFT JOIN users u ON c.country_id = u.country_id
GROUP BY c.name
ORDER BY total_users DESC;

-- вывести топ опросов по количеству прохождений и где есть хотя бы 1 ответ
SELECT 
    s.title, 
    COUNT(r.response_id) AS responses_count
FROM surveys s
JOIN survey_responses r ON s.survey_id = r.survey_id
GROUP BY s.survey_id, s.title
HAVING COUNT(r.response_id) > 0
ORDER BY responses_count DESC;

-- узнать средний возраст для каждого опроса
SELECT 
    s.title,
    ROUND(AVG(EXTRACT(YEAR FROM AGE(u.birth_date))), 1) AS avg_respondent_age
FROM surveys s
JOIN survey_responses r ON s.survey_id = r.survey_id
JOIN users u ON r.user_id = u.user_id
WHERE u.birth_date IS NOT NULL
GROUP BY s.survey_id, s.title;