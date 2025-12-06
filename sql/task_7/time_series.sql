-- Анализ временных рядов

-- 1. Выявление динамики: Количество прохождений опросов по дням
-- Позволяет увидеть пики активности.
SELECT 
    DATE(completed_at) AS response_date,
    COUNT(*) AS daily_responses
FROM survey_responses
WHERE completed_at IS NOT NULL
GROUP BY DATE(completed_at)
ORDER BY response_date;

-- 2. Динамика по категориям (Странам) для линейной диаграммы
-- Используем оконные функции для нарастающего итога внутри каждой страны.
SELECT 
    DATE(r.completed_at) AS response_date,
    c.name AS country,
    COUNT(*) AS daily_count,
    -- Нарастающий итог (Cumulative Sum) по стране
    SUM(COUNT(*)) OVER (PARTITION BY c.name ORDER BY DATE(r.completed_at)) AS cumulative_count
FROM survey_responses r
JOIN users u ON r.user_id = u.user_id
JOIN countries c ON u.country_id = c.country_id
WHERE r.completed_at IS NOT NULL
GROUP BY DATE(r.completed_at), c.name
ORDER BY response_date;

-- 3. Поиск закономерностей: Скользящее среднее (Moving Average)
-- Сглаживаем данные (среднее за текущий день + 2 предыдущих), чтобы убрать шум.
SELECT 
    DATE(completed_at) AS response_date,
    COUNT(*) AS daily_count,
    -- Среднее за 3 дня (текущий + 2 до него)
    ROUND(AVG(COUNT(*)) OVER (
        ORDER BY DATE(completed_at) 
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 1) AS moving_avg_3days
FROM survey_responses
WHERE completed_at IS NOT NULL
GROUP BY DATE(completed_at);

-- 4. Использование размерной таблицы дат (Date Dimension)
-- Генерируем серию дат, чтобы увидеть даже те дни, когда не было ответов (0 activity).
WITH date_series AS (
    SELECT generate_series(
        (SELECT MIN(DATE(completed_at)) FROM survey_responses), -- От первого ответа
        (SELECT MAX(DATE(completed_at)) FROM survey_responses), -- До последнего
        '1 day'::interval
    )::date AS calendar_date
)
SELECT 
    ds.calendar_date,
    COUNT(r.response_id) AS daily_activity,
    -- Накопительный итог
    SUM(COUNT(r.response_id)) OVER (ORDER BY ds.calendar_date) AS running_total
FROM date_series ds
LEFT JOIN survey_responses r ON DATE(r.completed_at) = ds.calendar_date
GROUP BY ds.calendar_date
ORDER BY ds.calendar_date;

-- 5. Сравнение периодов (YOY, MOM, DOD)

-- 5.1. DOD (Day-Over-Day) - День к дню
WITH daily_stats AS (
    SELECT DATE(completed_at) AS dt, COUNT(*) AS cnt
    FROM survey_responses WHERE completed_at IS NOT NULL
    GROUP BY DATE(completed_at)
)
SELECT 
    dt, cnt,
    LAG(cnt) OVER (ORDER BY dt) AS prev_day,
    ROUND((cnt - LAG(cnt) OVER (ORDER BY dt))::numeric / NULLIF(LAG(cnt) OVER (ORDER BY dt), 0) * 100, 1) AS dod_growth_pct
FROM daily_stats;


-- 5.2. MOM (Month-Over-Month) - Месяц к месяцу
-- Сначала группируем данные по месяцам
WITH monthly_stats AS (
    SELECT 
        DATE_TRUNC('month', completed_at)::date AS mth, -- Начало месяца
        COUNT(*) AS cnt
    FROM survey_responses 
    WHERE completed_at IS NOT NULL
    GROUP BY DATE_TRUNC('month', completed_at)
)
SELECT 
    TO_CHAR(mth, 'YYYY-MM') AS month_label,
    cnt AS current_month_count,
    -- Берем значение 1 строку назад (предыдущий месяц)
    LAG(cnt) OVER (ORDER BY mth) AS prev_month_count,
    -- Считаем % роста
    ROUND(
        (cnt - LAG(cnt) OVER (ORDER BY mth))::numeric / 
        NULLIF(LAG(cnt) OVER (ORDER BY mth), 0) * 100, 
    1) AS mom_growth_pct
FROM monthly_stats;


-- 5.3. YOY (Year-Over-Year) - Год к году
-- Сначала группируем данные по годам
WITH yearly_stats AS (
    SELECT 
        DATE_TRUNC('year', completed_at)::date AS yr, 
        COUNT(*) AS cnt
    FROM survey_responses 
    WHERE completed_at IS NOT NULL
    GROUP BY DATE_TRUNC('year', completed_at)
)
SELECT 
    TO_CHAR(yr, 'YYYY') AS year_label,
    cnt AS current_year_count,
    -- Берем значение 1 строку назад (предыдущий год)
    LAG(cnt) OVER (ORDER BY yr) AS prev_year_count,
    -- Считаем % роста
    ROUND(
        (cnt - LAG(cnt) OVER (ORDER BY yr))::numeric / 
        NULLIF(LAG(cnt) OVER (ORDER BY yr), 0) * 100, 
    1) AS yoy_growth_pct
FROM yearly_stats;