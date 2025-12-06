-- Цель: Понять, как долго пользователи остаются активными на платформе.
-- Когорта = Месяц регистрации пользователя.
-- Активность = Прохождение опроса.

WITH user_cohorts AS (
    -- 1. Определяем когорту для каждого пользователя (месяц регистрации)
    SELECT 
        user_id,
        DATE_TRUNC('month', registration_date)::date AS cohort_month
    FROM users
),
user_activities AS (
    -- 2. Собираем все месяцы, когда пользователи были активны (проходили опросы)
    SELECT 
        user_id,
        DATE_TRUNC('month', completed_at)::date AS activity_month
    FROM survey_responses
    WHERE completed_at IS NOT NULL
    GROUP BY user_id, DATE_TRUNC('month', completed_at)
),
cohort_activities AS (
    -- 3. Соединяем когорты с активностями
    SELECT 
        c.user_id,
        c.cohort_month,
        a.activity_month,
        -- Вычисляем "возраст" активности (Month Lag)
        -- 0 = активность в месяц регистрации
        -- 1 = активность через месяц и т.д.
        EXTRACT(YEAR FROM age(a.activity_month, c.cohort_month)) * 12 + 
        EXTRACT(MONTH FROM age(a.activity_month, c.cohort_month)) AS month_number
    FROM user_cohorts c
    JOIN user_activities a ON c.user_id = a.user_id
    -- Нас интересует активность только ПОСЛЕ или в МЕСЯЦ регистрации
    WHERE a.activity_month >= c.cohort_month
),
cohort_size AS (
    -- 4. Считаем исходный размер каждой когорты (сколько людей пришло)
    SELECT 
        cohort_month,
        COUNT(*) AS total_users
    FROM user_cohorts
    GROUP BY cohort_month
)

-- 5. Финальный отчет: Когорта | Месяц жизни | Активных юзеров | Retention Rate %
SELECT 
    TO_CHAR(ca.cohort_month, 'YYYY-MM') AS cohort,
    cs.total_users AS cohort_size,
    ca.month_number AS months_since_reg,
    COUNT(DISTINCT ca.user_id) AS active_users,
    -- Retention Rate = (Активные / Всего в когорте) * 100
    ROUND(COUNT(DISTINCT ca.user_id)::numeric / cs.total_users * 100, 1) AS retention_rate_pct
FROM cohort_activities ca
JOIN cohort_size cs ON ca.cohort_month = cs.cohort_month
GROUP BY ca.cohort_month, cs.total_users, ca.month_number
ORDER BY ca.cohort_month, ca.month_number;