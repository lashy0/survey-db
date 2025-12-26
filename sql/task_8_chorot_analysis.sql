-- Когортный анализ

-- определяем когорту для каждого пользователя, месяц регистрации
WITH user_cohorts AS (
    SELECT 
        user_id,
        DATE_TRUNC('month', registration_date)::date AS cohort_month
    FROM users
),
-- сбор всех месяцов, когда пользователи проходили опросы
user_activities AS (
    SELECT 
        user_id,
        DATE_TRUNC('month', completed_at)::date AS activity_month
    FROM survey_responses
    WHERE completed_at IS NOT NULL
    GROUP BY user_id, DATE_TRUNC('month', completed_at)
),
-- соединяем когорты с активностями и считаем время активности
cohort_activities AS (
    SELECT 
        c.user_id,
        c.cohort_month,
        a.activity_month,
        EXTRACT(YEAR FROM age(a.activity_month, c.cohort_month)) * 12 + 
        EXTRACT(MONTH FROM age(a.activity_month, c.cohort_month)) AS month_number
    FROM user_cohorts c
    JOIN user_activities a ON c.user_id = a.user_id
    WHERE a.activity_month >= c.cohort_month
),
-- считаем исходный размер каждой когорты, сколько людей пришло в этом месяце
cohort_size AS (
    SELECT 
        cohort_month,
        COUNT(*) AS total_users
    FROM user_cohorts
    GROUP BY cohort_month
)
SELECT 
    TO_CHAR(ca.cohort_month, 'YYYY-MM') AS cohort,
    cs.total_users AS cohort_size,
    ca.month_number AS months_since_reg,
    COUNT(DISTINCT ca.user_id) AS active_users,
    ROUND(COUNT(DISTINCT ca.user_id)::numeric / cs.total_users * 100, 1) AS retention_rate_pct
FROM cohort_activities ca
JOIN cohort_size cs ON ca.cohort_month = cs.cohort_month
GROUP BY ca.cohort_month, cs.total_users, ca.month_number
ORDER BY ca.cohort_month, ca.month_number;