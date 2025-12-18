import asyncio
import random
from datetime import date, datetime, timedelta, timezone
import sys
import os

sys.path.append(os.getcwd())

from faker import Faker
from sqlalchemy import text, select
from sqlalchemy.orm import selectinload  # <--- Магия оптимизации
from app.core.database import async_session_maker, engine
from app.models import (
    User, Country, Tag, Survey, Question, Option, 
    SurveyResponse, UserAnswer, SurveyStatus, UserRole, 
    QuestionType
)
from app.core.security import get_password_hash

fake = Faker('ru_RU')

NUM_USERS = 50
NUM_RESPONSES = 500  # Увеличил, так как теперь это будет быстро
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
    countries = [Country(name=name) for name in ['Россия', 'Беларусь', 'Казахстан', 'Узбекистан', 'Германия', 'США']]
    session.add_all(countries)
    tags = [Tag(name=name) for name in ['IT', 'Здоровье', 'Гейминг', 'Образование', 'Работа', 'Психология', 'Маркетинг']]
    session.add_all(tags)
    await session.commit()
    
    return (
        (await session.execute(select(Country))).scalars().all(),
        (await session.execute(select(Tag))).scalars().all()
    )

async def create_users(session, countries):
    print(f"👥 Создание {NUM_USERS} пользователей...")
    hashed_pw = get_password_hash(DEFAULT_PASSWORD)
    
    users_batch = []
    
    # Админ и Тестер
    users_batch.append(User(
        full_name="Главный Администратор", email="admin@main.com", password_hash=hashed_pw,
        birth_date=date(1990, 1, 1), city="Москва", country_id=countries[0].country_id, role=UserRole.admin
    ))
    users_batch.append(User(
        full_name="Иван Тестовый", email="user@test.com", password_hash=hashed_pw,
        birth_date=date(2000, 5, 20), city="Санкт-Петербург", country_id=countries[0].country_id, role=UserRole.user
    ))

    # Боты
    for _ in range(NUM_USERS):
        b_date = fake.date_of_birth(minimum_age=14, maximum_age=70) if random.random() > 0.3 else None
        users_batch.append(User(
            full_name=fake.name(),
            email=fake.unique.email(),
            password_hash=hashed_pw,
            birth_date=b_date,
            city=fake.city(),
            country_id=random.choice(countries).country_id,
            role=UserRole.user,
            registration_date=fake.date_time_between(start_date='-2y', end_date='now', tzinfo=timezone.utc)
        ))
    
    session.add_all(users_batch)
    await session.commit()
    
    # Возвращаем ID
    return (await session.execute(select(User.user_id))).scalars().all()

async def create_surveys(session, user_ids, tags):
    print("📝 Создание опросов...")
    author_id = user_ids[0]

    # ОПРОС 1
    s1 = Survey(
        title="Предпочтения в IT 2025", description="Исследование языков программирования.",
        status=SurveyStatus.active, author_id=author_id,
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
        start_date=datetime.now(timezone.utc) - timedelta(days=20),
        end_date=datetime.now(timezone.utc) + timedelta(days=60)
    )
    s1.tags.extend([tags[0], tags[4]])
    
    s1.questions = [
        Question(question_text="Ваш основной язык?", question_type=QuestionType.single_choice, position=1, 
                 options=[Option(option_text=t) for t in ["Python", "Java", "Go", "JavaScript", "C#"]]),
        Question(question_text="Ваш опыт работы?", question_type=QuestionType.single_choice, position=2,
                 options=[Option(option_text=t) for t in ["Junior", "Middle", "Senior", "Lead"]]),
        Question(question_text="Оцените удобство Python (1-5)", question_type=QuestionType.rating, position=3,
                 options=[Option(option_text=str(i)) for i in range(1, 6)])
    ]
    session.add(s1)

    # ОПРОС 2
    s2 = Survey(
        title="Игровая индустрия", description="Во что вы играете?",
        status=SurveyStatus.completed, author_id=author_id,
        created_at=datetime.now(timezone.utc) - timedelta(days=100),
        start_date=datetime.now(timezone.utc) - timedelta(days=90),
        end_date=datetime.now(timezone.utc) - timedelta(days=10)
    )
    s2.tags.append(tags[2])
    s2.questions = [
        Question(question_text="Любимый жанр?", question_type=QuestionType.single_choice, position=1,
                 options=[Option(option_text=t) for t in ["RPG", "Shooter", "Strategy", "Sim"]]),
        Question(question_text="На чем играете?", question_type=QuestionType.multiple_choice, position=2,
                 options=[Option(option_text=t) for t in ["PC", "PS5", "Xbox", "Switch", "Mobile"]])
    ]
    session.add(s2)
    await session.commit()

async def generate_responses(session, user_ids):
    print(f"🚀 Оптимизированная генерация {NUM_RESPONSES} ответов...")
    
    # 1. ЗАГРУЖАЕМ ВСЁ В ПАМЯТЬ ОДНИМ ЗАПРОСОМ (Eager Loading)
    # Загружаем опросы + вопросы + опции сразу
    stmt = select(Survey).options(
        selectinload(Survey.questions).selectinload(Question.options)
    )
    surveys_cache = (await session.execute(stmt)).scalars().all()
    
    if not surveys_cache:
        print("❌ Нет опросов для генерации ответов.")
        return

    existing_pairs = set()
    responses_to_add = []
    
    for i in range(NUM_RESPONSES):
        user_id = random.choice(user_ids)
        survey = random.choice(surveys_cache) # Используем загруженный объект
        
        if (user_id, survey.survey_id) in existing_pairs:
            continue
        existing_pairs.add((user_id, survey.survey_id))
        
        start_time = fake.date_time_between(start_date='-10d', end_date='now', tzinfo=timezone.utc)
        response = SurveyResponse(
            survey_id=survey.survey_id,
            user_id=user_id,
            started_at=start_time,
            completed_at=start_time + timedelta(seconds=random.randint(30, 600)),
            ip_address=fake.ipv4(),
            device_type=random.choice(["Desktop", "Mobile", "Tablet"])
        )
        
        # Генерация ответов БЕЗ запросов к БД
        user_answers = []
        for q in survey.questions: # Данные уже в памяти
            ans = UserAnswer(question_id=q.question_id)
            
            if q.question_type == QuestionType.text_answer:
                ans.text_answer = fake.sentence()
            elif q.options:
                # Просто берем random из списка опций в памяти
                if q.question_type == QuestionType.multiple_choice:
                     # Для простоты 1 вариант, но можно и больше
                     ans.selected_option_id = random.choice(q.options).option_id
                else:
                     ans.selected_option_id = random.choice(q.options).option_id
            
            user_answers.append(ans)
        
        response.answers = user_answers
        responses_to_add.append(response)
        
        # Печатаем прогресс каждые 50 записей
        if len(responses_to_add) % 50 == 0:
            print(f"   Подготовлено {len(responses_to_add)} / {NUM_RESPONSES}...")

    # Сохраняем пачкой
    session.add_all(responses_to_add)
    await session.commit()
    print(f"✅ Успешно сохранено {len(responses_to_add)} ответов.")

async def main():
    async with async_session_maker() as session:
        try:
            await clean_database(session)
            countries, tags = await create_countries_and_tags(session)
            user_ids = await create_users(session, countries)
            await create_surveys(session, user_ids, tags)
            await generate_responses(session, user_ids) # Передаем только ID, опросы сами загрузим
            
            print("\n🎉 ВСЕ ГОТОВО!")
            print(f"🔑 Admin: admin@main.com / {DEFAULT_PASSWORD}")
            print(f"🔑 User: user@test.com / {DEFAULT_PASSWORD}")
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            await session.rollback()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())