-- 1.  Напишите запрос для выявления динамики 

-- сколько опросов было пройдено в каждый конкретный день
SELECT 
    DATE(completed_at) AS response_date,
    COUNT(*) AS daily_responses
FROM survey_responses
WHERE completed_at IS NOT NULL
GROUP BY DATE(completed_at)
ORDER BY response_date;

-- 2.  Проанализируйте динамику по разным категориям и постройте линейную диаграмму с помощью оконных функций.

-- рост активности пользователей из разных стран
SELECT 
    DATE(r.completed_at) AS response_date,
    c.name AS country,
    COUNT(*) AS daily_count,
    SUM(COUNT(*)) OVER (PARTITION BY c.name ORDER BY DATE(r.completed_at)) AS cumulative_count
FROM survey_responses r
JOIN users u ON r.user_id = u.user_id
JOIN countries c ON u.country_id = c.country_id
WHERE r.completed_at IS NOT NULL
GROUP BY DATE(r.completed_at), c.name
ORDER BY response_date;

-- 3.  Поиск закономерностей (используйте скользящие временные ряды).

-- скользящее среднее
SELECT 
    DATE(completed_at) AS response_date,
    COUNT(*) AS daily_count,
    ROUND(AVG(COUNT(*)) OVER (
        ORDER BY DATE(completed_at) 
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 1) AS moving_avg_3days
FROM survey_responses
WHERE completed_at IS NOT NULL
GROUP BY DATE(completed_at)
ORDER BY response_date;

-- 4.  Примените размерную таблицу дат для нахождения статистических данных (среднее скользящее, накопительный итог).

-- генерация календаря от первого до последнего ответа
WITH date_series AS (
    SELECT generate_series(
        (SELECT MIN(DATE(completed_at)) FROM survey_responses), 
        (SELECT MAX(DATE(completed_at)) FROM survey_responses), 
        '1 day'::interval
    )::date AS calendar_date
)
SELECT 
    ds.calendar_date,
    COUNT(r.response_id) AS daily_activity,
    SUM(COUNT(r.response_id)) OVER (ORDER BY ds.calendar_date) AS running_total
FROM date_series ds
LEFT JOIN survey_responses r ON DATE(r.completed_at) = ds.calendar_date
GROUP BY ds.calendar_date
ORDER BY ds.calendar_date;

-- 5.  Сравнение YOY ((год к году, year-over-year) и Мом (месяц к месяцу, month-over-month), DOD ((день к дню, day-over-day)

-- DOD процент роста
WITH daily_stats AS (
    SELECT DATE(completed_at) AS dt, COUNT(*) AS cnt
    FROM survey_responses WHERE completed_at IS NOT NULL
    GROUP BY DATE(completed_at)
)
SELECT 
    dt, cnt,
    LAG(cnt) OVER (ORDER BY dt) AS prev_day,
    ROUND((cnt - LAG(cnt) OVER (ORDER BY dt))::numeric / NULLIF(LAG(cnt) OVER (ORDER BY dt), 0) * 100, 1) AS dod_growth_pct
FROM daily_stats
ORDER BY dt DESC LIMIT 10;

-- MOM процент роста
WITH monthly_stats AS (
    SELECT DATE_TRUNC('month', completed_at)::date AS mth, COUNT(*) AS cnt
    FROM survey_responses WHERE completed_at IS NOT NULL
    GROUP BY DATE_TRUNC('month', completed_at)
)
SELECT 
    TO_CHAR(mth, 'YYYY-MM') AS month_label,
    cnt AS current_month_count,
    LAG(cnt) OVER (ORDER BY mth) AS prev_month_count,
    ROUND((cnt - LAG(cnt) OVER (ORDER BY mth))::numeric / NULLIF(LAG(cnt) OVER (ORDER BY mth), 0) * 100, 1) AS mom_growth_pct
FROM monthly_stats
ORDER BY mth;

-- YOY процент роста
WITH yearly_stats AS (
    SELECT DATE_TRUNC('year', completed_at)::date AS yr, COUNT(*) AS cnt
    FROM survey_responses WHERE completed_at IS NOT NULL
    GROUP BY DATE_TRUNC('year', completed_at)
)
SELECT 
    TO_CHAR(yr, 'YYYY') AS year_label,
    cnt,
    LAG(cnt) OVER (ORDER BY yr) AS prev_year_cnt,
    ROUND((cnt - LAG(cnt) OVER (ORDER BY yr))::numeric / NULLIF(LAG(cnt) OVER (ORDER BY yr), 0) * 100, 1) AS yoy_growth_pct
FROM yearly_stats;