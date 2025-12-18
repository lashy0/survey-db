import asyncio
import random
from datetime import date, datetime, timedelta, timezone
import sys
import os

# Добавляем текущую директорию в путь, чтобы видеть app
sys.path.append(os.getcwd())

from faker import Faker
from sqlalchemy import text, select
from sqlalchemy.orm import selectinload
from app.core.database import async_session_maker
from app.models import (
    User, Country, Tag, Survey, Question, Option, 
    SurveyResponse, UserAnswer, SurveyStatus, UserRole, 
    QuestionType
)
from app.core.security import get_password_hash

fake = Faker('ru_RU')

# НАСТРОЙКИ ГЕНЕРАЦИИ
NUM_USERS = 50
NUM_SURVEYS_TO_CREATE = 12  # Количество опросов
RESPONSES_PER_USER_AVG = 4  # В среднем каждый юзер пройдет столько опросов (из 12)
DEFAULT_PASSWORD = "123456"

async def clean_database(session):
    print("🧹 Очистка базы данных...")
    tables = [
        "user_answers", "survey_responses", "options", "questions", 
        "survey_tags", "tags", "surveys", "users", "countries"
    ]
    for table in tables:
        await session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;"))
    await session.commit()

async def create_countries_and_tags(session):
    print("🌍 Создание стран и тегов...")
    countries_list = ['Россия', 'Беларусь', 'Казахстан', 'Узбекистан', 'Германия', 'США', 'Франция', 'Китай']
    countries = [Country(name=name) for name in countries_list]
    session.add_all(countries)

    tags_list = [
        'IT', 'Здоровье', 'Гейминг', 'Образование', 'Работа', 'Психология', 
        'Маркетинг', 'Кино', 'Путешествия', 'Еда', 'Спорт', 'Финансы'
    ]
    tags = [Tag(name=name) for name in tags_list]
    session.add_all(tags)
    
    await session.commit()
    
    # Возвращаем объекты для связей
    c_objs = (await session.execute(select(Country))).scalars().all()
    t_objs = (await session.execute(select(Tag))).scalars().all()
    return c_objs, t_objs

async def create_users(session, countries):
    print(f"👥 Создание {NUM_USERS} пользователей...")
    hashed_pw = get_password_hash(DEFAULT_PASSWORD)
    users_batch = []

    # 1. Админ
    users_batch.append(User(
        full_name="Главный Администратор", email="admin@main.com", password_hash=hashed_pw,
        birth_date=date(1990, 1, 1), city="Москва", country_id=countries[0].country_id, role=UserRole.admin
    ))
    
    # 2. Тестер (Для вашей проверки)
    users_batch.append(User(
        full_name="Иван Тестовый", email="user@test.com", password_hash=hashed_pw,
        birth_date=date(2000, 5, 20), city="Санкт-Петербург", country_id=countries[0].country_id, role=UserRole.user
    ))

    # 3. Массовка
    for _ in range(NUM_USERS):
        b_date = fake.date_of_birth(minimum_age=16, maximum_age=65) if random.random() > 0.1 else None
        users_batch.append(User(
            full_name=fake.name(),
            email=fake.unique.email(),
            password_hash=hashed_pw,
            birth_date=b_date,
            city=fake.city(),
            country_id=random.choice(countries).country_id,
            role=UserRole.user,
            registration_date=fake.date_time_between(start_date='-1y', end_date='now', tzinfo=timezone.utc)
        ))

    session.add_all(users_batch)
    await session.commit()
    
    # Возвращаем всех пользователей
    return (await session.execute(select(User))).scalars().all()

async def create_surveys(session, users, tags):
    print("📝 Создание разнообразных опросов...")
    # Берем админа как автора (первый в списке)
    author = users[0]
    
    # Шаблоны опросов (Название, Описание, Теги (индексы))
    templates = [
        ("Тренды IT 2025", "Какие языки и технологии будут популярны?", [0, 4]),
        ("Здоровый сон", "Как вы спите и что вам мешает?", [1, 5]),
        ("Любимые игры", "PC или Консоли? RPG или Шутеры?", [2, 0]),
        ("Качество образования", "Оцените ваш ВУЗ или школу.", [3, 4]),
        ("Удаленка vs Офис", "Где продуктивнее работать?", [4, 5]),
        ("Психология успеха", "Что мотивирует вас двигаться вперед?", [5, 4]),
        ("Лучшие фильмы года", "Что вы смотрели в этом году?", [7, 2]),
        ("Гастрономический тур", "Какую кухню вы предпочитаете?", [9, 8]),
        ("Финансовая грамотность", "Как вы ведете бюджет?", [11, 4]),
        ("Спорт для всех", "Как часто вы тренируетесь?", [10, 1]),
        ("Путешествия по России", "Где вы отдыхали этим летом?", [8, 7]),
        ("Маркетинг в соцсетях", "Какой контент вам нравится?", [6, 0])
    ]

    created_surveys = []
    
    for i, (title, desc, tag_indices) in enumerate(templates):
        # Статус: Почти все активные, пару завершенных для разнообразия
        status = SurveyStatus.active
        if i == 10: status = SurveyStatus.completed
        if i == 11: status = SurveyStatus.draft # Один черновик (не виден никому)

        s = Survey(
            title=title,
            description=desc,
            status=status,
            author_id=author.user_id,
            created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 100)),
            start_date=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 90)),
            end_date=datetime.now(timezone.utc) + timedelta(days=30)
        )
        
        # Добавляем теги
        for t_idx in tag_indices:
            if t_idx < len(tags):
                s.tags.append(tags[t_idx])
        
        # Добавляем вопросы (Генерируем 3 случайных вопроса)
        s.questions = [
            Question(question_text=f"Вопрос 1 для '{title}'?", question_type=QuestionType.single_choice, position=1, 
                     options=[Option(option_text=o) for o in ["Вариант А", "Вариант Б", "Вариант В"]]),
            Question(question_text=f"Вопрос 2 для '{title}'?", question_type=QuestionType.rating, position=2,
                     options=[Option(option_text=str(x)) for x in range(1, 6)]),
            Question(question_text="Ваше мнение (текст)?", question_type=QuestionType.text_answer, position=3)
        ]
        
        session.add(s)
        created_surveys.append(s)

    await session.commit()
    # Возвращаем объекты опросов с ID
    return (await session.execute(select(Survey))).scalars().all()

async def generate_sparse_responses(session, users, surveys):
    print(f"🚀 Генерация ответов (Разреженность: ~{RESPONSES_PER_USER_AVG} на пользователя)...")
    
    # Загружаем опросы полностью, чтобы иметь доступ к вопросам
    # (Хотя они у нас есть в surveys, но для надежности при detach)
    stmt = select(Survey).options(
        selectinload(Survey.questions).selectinload(Question.options)
    )
    surveys_full = (await session.execute(stmt)).scalars().all()
    # Фильтруем только активные/завершенные (черновики нельзя проходить)
    valid_surveys = [s for s in surveys_full if s.status != SurveyStatus.draft]

    responses_to_add = []
    
    # 1. Генерируем ответы для МАССОВКИ
    # Пропускаем админа (0) и Тестера (1) пока что
    for user in users[2:]:
        # Выбираем случайные N опросов (от 0 до 8), чтобы были "дыры" в данных
        num_to_take = random.randint(0, 8) 
        surveys_taken = random.sample(valid_surveys, min(num_to_take, len(valid_surveys)))
        
        for survey in surveys_taken:
            resp = create_single_response(user.user_id, survey)
            responses_to_add.append(resp)

    # 2. Генерируем ответы для ТЕСТЕРА (user@test.com)
    # ПУСТЬ ОН ПРОЙДЕТ ТОЛЬКО ПЕРВЫЕ 2 ОПРОСА
    # Остальные 8-9 останутся для рекомендаций!
    tester_user = users[1]
    for survey in valid_surveys[:2]:
        resp = create_single_response(tester_user.user_id, survey)
        responses_to_add.append(resp)

    session.add_all(responses_to_add)
    await session.commit()
    print(f"✅ Создано {len(responses_to_add)} прохождений опросов.")

def create_single_response(user_id, survey):
    """Вспомогательная функция создания объекта ответа"""
    start_time = fake.date_time_between(start_date='-10d', end_date='now', tzinfo=timezone.utc)

    if random.random() < 0.25:
        completed_at = None
    else:
        completed_at = start_time + timedelta(seconds=random.randint(60, 600))
    
    response = SurveyResponse(
        survey_id=survey.survey_id,
        user_id=user_id,
        started_at=start_time,
        completed_at=completed_at,
        ip_address=fake.ipv4(),
        device_type=random.choice(["Desktop", "Mobile"])
    )
    
    # Ответы на вопросы
    user_answers = []
    # Если опрос брошен, пользователь мог ответить не на все вопросы
    questions_to_answer = survey.questions
    if completed_at is None:
        # Ответит только на первые 0-1 вопрос
        limit = random.randint(0, len(survey.questions) - 1)
        questions_to_answer = survey.questions[:limit]

    for q in questions_to_answer:
        ans = UserAnswer(question_id=q.question_id)
        if q.question_type == QuestionType.text_answer:
            ans.text_answer = fake.sentence()
        elif q.options:
            ans.selected_option_id = random.choice(q.options).option_id
        user_answers.append(ans)
    
    response.answers = user_answers
    return response

async def main():
    async with async_session_maker() as session:
        try:
            await clean_database(session)
            countries, tags = await create_countries_and_tags(session)
            users = await create_users(session, countries)
            surveys = await create_surveys(session, users, tags)
            await generate_sparse_responses(session, users, surveys)
            
            print("\n🎉 БАЗА УСПЕШНО ЗАПОЛНЕНА!")
            print(f"🔑 Admin: admin@main.com / {DEFAULT_PASSWORD}")
            print(f"🔑 User:  user@test.com  / {DEFAULT_PASSWORD} (Пройдено 2 опроса из {len(surveys)})")
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            await session.rollback()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())