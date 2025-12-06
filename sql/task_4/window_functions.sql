-- 1. Запросы с применением оконных функций внутри окна

-- Ранжирование пользователей по возрасту внутри каждой страны.
-- (Кто самый молодой в России, в Беларуси и т.д.?)
-- Демонстрация: DENSE_RANK()
SELECT 
    c.name AS country,
    u.first_name,
    u.last_name,
    u.birth_date,
    DENSE_RANK() OVER (PARTITION BY u.country_id ORDER BY u.birth_date DESC) AS age_rank
FROM users u
JOIN countries c ON u.country_id = c.country_id;

-- Сравнение длительности прохождения опроса со средней длительностью по этому опросу.
-- (Позволяет найти тех, кто прошел слишком быстро или слишком медленно)
-- Демонстрация: AVG() OVER (PARTITION BY)
SELECT 
    s.title,
    u.last_name,
    r.duration,
    AVG(r.duration) OVER (PARTITION BY r.survey_id) AS avg_survey_duration,
    r.duration - AVG(r.duration) OVER (PARTITION BY r.survey_id) AS diff_from_avg
FROM survey_responses r
JOIN surveys s ON r.survey_id = s.survey_id
JOIN users u ON r.user_id = u.user_id;

-- Нумерация вопросов внутри каждого опроса
-- (Даже если ID вопросов идут не по порядку, мы создадим свою нумерацию 1, 2, 3...)
-- Демонстрация: ROW_NUMBER()
SELECT 
    s.title,
    q.question_text,
    ROW_NUMBER() OVER (PARTITION BY s.survey_id ORDER BY q.position) AS question_number
FROM questions q
JOIN surveys s ON q.survey_id = s.survey_id;


-- 2. Запросы с накомплением значений внутри окон

-- Кумулятивный (нарастающий) итог регистраций пользователей по месяцам.
-- (Показывает, как росла база пользователей со временем)
SELECT 
    TO_CHAR(registration_date, 'YYYY-MM') AS reg_month,
    COUNT(*) AS new_users_in_month,
    SUM(COUNT(*)) OVER (
        ORDER BY TO_CHAR(registration_date, 'YYYY-MM') 
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS total_users_cumulative
FROM users
GROUP BY TO_CHAR(registration_date, 'YYYY-MM');

-- Накопительное количество прохождений опросов по дням.
-- (Динамика активности на платформе)
SELECT 
    DATE(completed_at) AS response_date,
    COUNT(*) AS daily_responses,
    SUM(COUNT(*)) OVER (
        ORDER BY DATE(completed_at)
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total_responses
FROM survey_responses
WHERE completed_at IS NOT NULL
GROUP BY DATE(completed_at);