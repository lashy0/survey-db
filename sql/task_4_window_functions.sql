-- 1. Запросы с применением оконных функций внутри окна

-- ранжирование пользователей по возрасту внутри каждой страны
SELECT 
    c.name AS country,
    u.full_name,
    u.birth_date,
    DENSE_RANK() OVER (
        PARTITION BY u.country_id 
        ORDER BY u.birth_date DESC NULLS LAST
    ) AS age_rank
FROM users u
JOIN countries c ON u.country_id = c.country_id;

-- сравнение времени прохождения со средним по опросу
SELECT 
    s.title AS survey_title,
    u.full_name,
    r.duration,
    AVG(r.duration) OVER (PARTITION BY r.survey_id) AS survey_avg_duration,
    r.duration - AVG(r.duration) OVER (PARTITION BY r.survey_id) AS diff_from_avg
FROM survey_responses r
JOIN surveys s ON r.survey_id = s.survey_id
JOIN users u ON r.user_id = u.user_id
WHERE r.completed_at IS NOT NULL
ORDER BY s.title, diff_from_avg;

-- 2. Запросы с накомплением значений внутри окон

-- накопительный итог регистрации по месяцам
SELECT 
    TO_CHAR(registration_date, 'YYYY-MM') AS reg_month,
    COUNT(*) AS new_users_in_month,
    SUM(COUNT(*)) OVER (
        ORDER BY TO_CHAR(registration_date, 'YYYY-MM') 
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS total_users_cumulative
FROM users
GROUP BY TO_CHAR(registration_date, 'YYYY-MM')
ORDER BY reg_month;

-- накопительный активности по дням
SELECT 
    DATE(completed_at) AS response_date,
    COUNT(*) AS daily_responses,
    SUM(COUNT(*)) OVER (
        ORDER BY DATE(completed_at)
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total_responses
FROM survey_responses
WHERE completed_at IS NOT NULL
GROUP BY DATE(completed_at)
ORDER BY response_date;

