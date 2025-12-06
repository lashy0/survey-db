-- 1. Простые запросы с условием (операторы сравнения, and, or, like, ilke, similar to, between, in и др.)

-- найти всех пользователей из Москвы
SELECT * 
FROM users 
WHERE city = 'Москва';

-- найти опросы, которые сейчас активны (status = 'active') ИЛИ являются черновиками (status = 'draft')
SELECT title, status, created_at 
FROM surveys 
WHERE status IN ('active', 'draft');

-- найти пользователей, у которых email находится в домене @yandex.ru
SELECT first_name, last_name, email 
FROM users 
WHERE email LIKE '%@yandex.ru';

-- найти города, название которых начинается на "Санкт-"
SELECT DISTINCT city 
FROM users 
WHERE city ILIKE 'санкт-%';

-- найти пользователей, родившихся в период с 1990 по 2000 год
SELECT email, birth_date 
FROM users 
WHERE birth_date BETWEEN '1990-01-01' AND '2000-12-31';

-- найти опросы, у которых дата окончания больше текущей даты (еще не закончились)
SELECT title, end_date 
FROM surveys 
WHERE end_date > NOW();


-- 2. Запросы с применением функций для работы со строками, датами, функциями преобразования и др.

-- вывести возраст каждого пользователя
SELECT 
    email, 
    birth_date,
    EXTRACT(YEAR FROM AGE(birth_date)) AS exact_age 
FROM users;

-- преобразовать email в верхний регистр и вывести длину пароля
SELECT 
    UPPER(email) AS email_upper, 
    LENGTH(password_hash) AS password_length 
FROM users;

-- вывести дату регистрации в формате "День-Месяц-Год"
SELECT 
    email, 
    TO_CHAR(registration_date, 'DD-MM-YYYY HH24:MI') AS formatted_reg_date 
FROM users;

-- обработка NULL значений: Вывести город, а если он не указан - написать 'Не указан'
SELECT 
    email, 
    COALESCE(city, 'Не указан') AS city_check 
FROM users;


-- 3. Запросы с агрегатными функциями, с группировкой данных, с условием для отбора групп

-- посчитать количество пользователей в каждом городе
SELECT 
    city, 
    COUNT(*) AS users_count 
FROM users 
GROUP BY city 
ORDER BY users_count DESC;

-- найти самый ранний и самый поздний год рождения среди пользователей
SELECT 
    MIN(birth_date) AS oldest_birth_date, 
    MAX(birth_date) AS youngest_birth_date 
FROM users;

-- показать только те города, где больше 1 пользователя
SELECT 
    city, 
    COUNT(*) AS users_count 
FROM users 
GROUP BY city 
HAVING COUNT(*) > 1;

-- посчитать, сколько опросов в каждом статусе (draft, active...)
SELECT 
    status, 
    COUNT(*) AS surveys_count 
FROM surveys 
GROUP BY status;