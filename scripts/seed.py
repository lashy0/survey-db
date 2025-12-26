import asyncio
import random
import sys
import json
import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from faker import Faker
from sqlalchemy import text, select
from sqlalchemy.orm import selectinload

# Rich Imports
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.traceback import install

# Установка обработчика ошибок
install(show_locals=False)

# Импорты приложения
from app.core.database import async_session_maker
from app.models import (
    User, Country, Tag, Survey, Question, Option, 
    SurveyResponse, UserAnswer, SurveyStatus, UserRole, 
    QuestionType
)
from app.core.security import get_password_hash

# --- GLOBAL CONFIG ---
fake = Faker('ru_RU')
console = Console()
DEFAULT_PASSWORD = "123456"

# --- ФУНКЦИИ ---

def parse_args():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description="Скрипт для заполнения БД тестовыми данными (Seeding)")
    
    parser.add_argument(
        "--users", 
        type=int, 
        default=50, 
        help="Количество ботов для генерации (по умолчанию: 50)"
    )
    
    parser.add_argument(
        "--no-clean", 
        action="store_true", 
        help="Не очищать базу данных перед началом (добавить данные к существующим)"
    )
    
    parser.add_argument(
        "--file", 
        type=str, 
        default=None, 
        help="Путь к JSON файлу с опросами (по умолчанию: app/data/surveys.json)"
    )

    return parser.parse_args()

def load_scenarios(custom_path=None):
    """Загружает данные опросов из JSON файла"""
    try:
        if custom_path:
            file_path = Path(custom_path)
        else:
            # Путь по умолчанию: app/data/surveys.json
            base_dir = Path(__file__).resolve().parent.parent
            file_path = base_dir / "data" / "surveys.json"
        
        if not file_path.exists():
            console.print(f"[bold red]Файл не найден: {file_path}[/bold red]")
            sys.exit(1)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        console.print(f"[bold red]Ошибка формата JSON: {e}[/bold red]")
        sys.exit(1)

async def clean_database(session):
    """Полная очистка таблиц"""
    with console.status("[bold red]Очистка базы данных...", spinner="dots"):
        tables = [
            "user_answers", "survey_responses", "options", "questions", 
            "survey_tags", "tags", "surveys", "users", "countries"
        ]
        for table in tables:
            await session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;"))
        await session.commit()
    console.print("[green]База данных очищена[/green]")

async def create_countries_and_tags(session):
    """Создание справочников (пропускаем если уже есть)"""
    # Простая проверка, чтобы не дублировать, если --no-clean
    existing = (await session.execute(select(Country))).first()
    if existing:
        console.print("ℹ[dim]Справочники уже существуют, пропускаем...[/dim]")
        c_objs = (await session.execute(select(Country))).scalars().all()
        t_objs = (await session.execute(select(Tag))).scalars().all()
        return c_objs, t_objs

    with console.status("[bold blue]Создание справочников...", spinner="earth"):
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
        
        c_objs = (await session.execute(select(Country))).scalars().all()
        t_objs = (await session.execute(select(Tag))).scalars().all()
    
    console.print(f"[green]Добавлено:[/green] {len(c_objs)} стран, {len(t_objs)} тегов")
    return c_objs, t_objs

async def create_users(session, countries, num_bots):
    """Генерация пользователей"""
    users_batch = []
    hashed_pw = get_password_hash(DEFAULT_PASSWORD)
    
    console.print(f"[bold cyan]Генерация {num_bots} ботов + 2 админов...[/bold cyan]")
    
    # Проверка на существование Admin (чтобы не упало при --no-clean)
    admin_exists = (await session.execute(select(User).where(User.email == "admin@main.com"))).first()
    
    if not admin_exists:
        # 1. Админ
        users_batch.append(User(
            full_name="Главный Администратор", email="admin@main.com", password_hash=hashed_pw,
            birth_date=date(1990, 1, 1), city="Москва", country_id=countries[0].country_id, role=UserRole.admin
        ))
        # 2. Тестер
        users_batch.append(User(
            full_name="Иван Тестовый", email="user@test.com", password_hash=hashed_pw,
            birth_date=date(2000, 5, 20), city="Санкт-Петербург", country_id=countries[0].country_id, role=UserRole.user
        ))
    
    # 3. Боты
    for _ in range(num_bots):
        b_date = fake.date_of_birth(minimum_age=16, maximum_age=65) if random.random() > 0.1 else None
        users_batch.append(User(
            full_name=fake.name(),
            email=fake.unique.email(), # Faker гарантирует уникальность в рамках сессии
            password_hash=hashed_pw,
            birth_date=b_date,
            city=fake.city(),
            country_id=random.choice(countries).country_id,
            role=UserRole.user,
            registration_date=fake.date_time_between(start_date='-1y', end_date='now', tzinfo=timezone.utc)
        ))
    
    session.add_all(users_batch)
    await session.commit()
    
    all_users = (await session.execute(select(User))).scalars().all()
    return all_users

async def create_surveys(session, users, tags, json_path=None):
    """Создание опросов из JSON"""
    scenarios = load_scenarios(json_path)
    
    # Чтобы не дублировать опросы при --no-clean, проверим названия
    existing_titles = (await session.execute(select(Survey.title))).scalars().all()
    
    # Фильтруем те, которых нет в базе
    new_scenarios = [s for s in scenarios if s['title'] not in existing_titles]
    
    if not new_scenarios:
        console.print("ℹ[dim]Все опросы из файла уже существуют.[/dim]")
        return (await session.execute(select(Survey))).scalars().all()

    with console.status(f"[bold yellow]Загрузка {len(new_scenarios)} новых опросов...", spinner="flip"):
        author = users[0] # Админ
        
        for i, data in enumerate(new_scenarios):
            status = SurveyStatus.active
            if i >= len(scenarios) - 2: status = SurveyStatus.completed
            
            s = Survey(
                title=data["title"],
                description=data["desc"],
                status=status,
                author_id=author.user_id,
                created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(20, 120)),
                start_date=datetime.now(timezone.utc) - timedelta(days=random.randint(10, 100)),
                end_date=datetime.now(timezone.utc) + timedelta(days=30)
            )
            
            for t_idx in data.get("tags", []):
                if t_idx < len(tags):
                    s.tags.append(tags[t_idx])
            
            questions_objects = []
            for q_idx, q_data in enumerate(data.get("questions", [])):
                q_type_enum = QuestionType.single_choice
                type_str = q_data["type"]
                
                if type_str == "multiple_choice": q_type_enum = QuestionType.multiple_choice
                elif type_str == "text_answer": q_type_enum = QuestionType.text_answer
                elif type_str == "rating": q_type_enum = QuestionType.rating
                
                quest = Question(
                    question_text=q_data["text"],
                    question_type=q_type_enum,
                    position=q_idx + 1
                )
                
                if "options" in q_data:
                    quest.options = [Option(option_text=opt) for opt in q_data["options"]]
                elif q_type_enum == QuestionType.rating:
                    scale = q_data.get("scale", 5)
                    quest.options = [Option(option_text=str(x)) for x in range(1, scale + 1)]
                
                questions_objects.append(quest)
            
            s.questions = questions_objects
            session.add(s)
            
        await session.commit()
    
    surveys = (await session.execute(select(Survey))).scalars().all()
    console.print(f"[green]Всего опросов в базе: {len(surveys)}[/green]")
    return surveys

def create_single_response(user_id, survey, user_reg_date):
    """Генерация объекта ответа"""
    rand = random.random()
    if rand < 0.6: lag_days = random.randint(0, 30)
    elif rand < 0.8: lag_days = random.randint(31, 60)
    else: lag_days = random.randint(91, 180)
    
    start_time = user_reg_date + timedelta(days=lag_days)
    if start_time > datetime.now(timezone.utc):
        start_time = datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 24))
        
    completed_at = None if random.random() < 0.15 else start_time + timedelta(seconds=random.randint(45, 900))
    
    response = SurveyResponse(
        survey_id=survey.survey_id,
        user_id=user_id,
        started_at=start_time,
        completed_at=completed_at,
        ip_address=fake.ipv4(),
        device_type=random.choice(["Desktop", "Mobile", "Tablet"])
    )
    
    user_answers = []
    questions_to_answer = survey.questions
    
    if completed_at is None:
        limit = random.randint(0, max(0, len(survey.questions) - 1))
        questions_to_answer = survey.questions[:limit]
        
    for q in questions_to_answer:
        if q.question_type == QuestionType.multiple_choice and q.options:
             opts = random.sample(q.options, k=random.randint(1, min(3, len(q.options))))
             for opt in opts:
                 user_answers.append(UserAnswer(question_id=q.question_id, selected_option_id=opt.option_id))
        else:
            ans = UserAnswer(question_id=q.question_id)
            if q.question_type == QuestionType.text_answer:
                ans.text_answer = fake.sentence(nb_words=random.randint(5, 15))
                user_answers.append(ans)
            elif q.options:
                ans.selected_option_id = random.choice(q.options).option_id
                user_answers.append(ans)
                
    response.answers = user_answers
    return response

async def generate_responses(session, users, surveys):
    """Массовая генерация ответов"""
    stmt = select(Survey).options(
        selectinload(Survey.questions).selectinload(Question.options)
    )
    surveys_full = (await session.execute(stmt)).scalars().all()
    valid_surveys = [s for s in surveys_full if s.status != SurveyStatus.draft]
    
    # Берем только пользователей, у которых еще мало ответов (для --no-clean)
    # Но для простоты симуляции - просто генерируем для всех ботов
    # (Боты в списке users это объекты SQLAlchemy, если они только что созданы - ответов нет)
    
    # Фильтруем админов (первые 2 обычно, но лучше проверить по роли)
    bots = [u for u in users if u.role == UserRole.user and u.email != 'user@test.com']
    tester = next((u for u in users if u.email == 'user@test.com'), None)
    
    responses_to_add = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task_bots = progress.add_task("[magenta]Активность ботов...", total=len(bots))
        
        for bot in bots:
            num_to_take = random.randint(2, 6)
            surveys_taken = random.sample(valid_surveys, min(num_to_take, len(valid_surveys)))
            for survey in surveys_taken:
                resp = create_single_response(bot.user_id, survey, bot.registration_date)
                responses_to_add.append(resp)
            progress.advance(task_bots)
            
        if tester:
            target_surveys = [s for s in valid_surveys if "IT" in s.title or "Игры" in s.title]
            for survey in target_surveys:
                resp = create_single_response(tester.user_id, survey, tester.registration_date)
                responses_to_add.append(resp)

    if responses_to_add:
        with console.status(f"[bold magenta]Сохранение {len(responses_to_add)} ответов...", spinner="bouncingBall"):
            session.add_all(responses_to_add)
            await session.commit()
        console.print(f"[green]Сгенерировано {len(responses_to_add)} сессий ответов[/green]")
    else:
        console.print("ℹ[dim]Нет новых пользователей для генерации ответов.[/dim]")

async def main():
    args = parse_args()
    
    if args.no_clean:
        console.print("[bold yellow]Режим Append: База данных НЕ будет очищена[/bold yellow]")
    
    async with async_session_maker() as session:
        try:
            if not args.no_clean:
                await clean_database(session)
            
            console.print("―" * 30, style="dim")
            
            countries, tags = await create_countries_and_tags(session)
            console.print("―" * 30, style="dim")
            
            # Передаем количество ботов из аргументов
            users = await create_users(session, countries, args.users)
            console.print("―" * 30, style="dim")
            
            # Передаем путь к файлу (если есть)
            surveys = await create_surveys(session, users, tags, args.file)
            console.print("―" * 30, style="dim")
            
            await generate_responses(session, users, surveys)
            
            # Финальная таблица
            table = Table(title="Данные для входа", show_header=True, header_style="bold magenta", border_style="green")
            table.add_column("Роль", style="cyan", justify="right")
            table.add_column("Email", style="bold white")
            table.add_column("Пароль", style="dim")
            
            table.add_row("Admin", "admin@main.com", DEFAULT_PASSWORD)
            table.add_row("User", "user@test.com", DEFAULT_PASSWORD)
            
            console.print("\n")
            console.print(table)
            console.print("\n[bold green]Данные успешно загружены![/bold green]")
            
        except Exception:
            console.print_exception()
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(main())
