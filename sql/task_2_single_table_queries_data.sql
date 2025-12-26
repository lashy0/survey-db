-- 1. Простые запросы с условием

-- поиск пользователей из конкретного города
SELECT * 
FROM users 
WHERE city = 'Москва';

-- поиск опросов, которые либо активны, либо являются черновиками
SELECT title, status, created_at 
FROM surveys 
WHERE status IN ('active', 'draft');

-- поиск пользователей с определенной почтой
SELECT full_name, email 
FROM users 
WHERE email LIKE '%@main.com';

-- поиск городов, начинающихся на "Санкт-", без учета регистра
SELECT DISTINCT city 
FROM users 
WHERE city ILIKE 'санкт-%';

-- поиск пользователей, родившихся в 90-е
SELECT email, birth_date 
FROM users 
WHERE birth_date BETWEEN '1990-01-01' AND '2000-12-31';

-- поиск вопросов, текст которых начинается с "Как" или "Что"
SELECT question_text 
FROM questions 
WHERE question_text SIMILAR TO '(Как|Что)%';

-- 2. Запросы с применением функций

-- расчет точного возраста пользователя
SELECT 
    full_name, 
    birth_date,
    EXTRACT(YEAR FROM AGE(birth_date)) AS exact_age 
FROM users;

-- работа со строками: Приведение email к верхнему регистру и подсчет длины пароля
SELECT 
    UPPER(email) AS email_upper, 
    LENGTH(password_hash) AS hash_length 
FROM users;

-- форматирование даты регистрации в удобный вид
SELECT 
    email, 
    TO_CHAR(registration_date, 'DD-MM-YYYY HH24:MI') AS formatted_reg_date 
FROM users;

-- 3. Запросы с агрегатными функциями и группировкой

-- подсчет количества пользователей в каждом городе
SELECT 
    city, 
    COUNT(*) AS users_count 
FROM users 
GROUP BY city 
ORDER BY users_count DESC;

-- поиск самого старого и самого молодого пользователя
SELECT 
    MIN(birth_date) AS oldest_birth_date, 
    MAX(birth_date) AS youngest_birth_date 
FROM users;

-- статистика по статусам опросов
SELECT 
    status, 
    COUNT(*) AS surveys_count 
FROM surveys 
GROUP BY status;