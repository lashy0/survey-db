# Survey Platform

A comprehensive full-stack application for creating, managing, and analyzing surveys. Built with FastAPI and PostgreSQL,
utilizing HTMX for dynamic frontend interactions and Plotly for analytics.

## Project Structure

```
.
├── app/
│   ├── core/               # Config, database, security, and middleware
│   ├── models.py           # SQLAlchemy ORM models
│   ├── routers/            # API endpoints (Auth, Users, Surveys, Admin)
│   ├── services/           # Business logic
│   ├── templates/          # Jinja2 HTML templates (HTMX + Tailwind)
│   └── main.py             # Application entry point
├── scripts/
│   ├── seed.py             # Database seeder CLI
├── data/                   # JSON data files (e.g., surveys.json)
├── alembic/                # Database migrations
├── sql/                    # Raw SQL queries for educational tasks (Analysis, Optimization)
├── tests/                  # Pytest suite
├── docker-compose.prod.yml # Production setup (App + DB + Caddy)
├── docker-compose.dev.yml  # Development setup (DB only)
└── pyproject.toml          # Dependencies (managed by uv)
```

## Configuration

Create a `.env` file in the root directory. You can use the example below:

```ini
# Application Config
DB_USER=postgres
DB_PASS=postgres
DB_NAME=postgres
# In Docker (Prod), this is overridden to 'db'. In Dev, it is 'localhost'.
DB_HOST=localhost 

# Security
SECRET_KEY=generate_a_secure_random_string_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Deployment (Required for Caddy in docker-compose.yml)
# Use 'localhost' for local testing, or your real domain (e.g., mysite.com) for VPS
DOMAIN=localhost
```

## Getting Started

### Full Stack (Production/VPS)

Run the Database, Application, and Web Server (Caddy) in containers.

#### 1. Start the stack

```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

#### 2. Apply Migrations and Seed Data

Must be run inside the container.

```bash
# Apply database schema
docker compose -f docker-compose.prod.yml exec app alembic upgrade head

# Fill DB with test users and surveys
docker compose -f docker-compose.prod.yml exec app python -m scripts.seed
```

#### 3. Access

Open your browser at `http://localhost` (or your configured `${DOMAIN}`).

### Local Development

Run the Database in Docker, but run the FastAPI app locally for debugging.

#### 1. Install Dependencies

Using `uv` (recommended) or pip:

```bash
uv sync
# or
pip install .
```

#### 2. Start Database Only

Use the dev-specific compose file.

```bash
docker-compose -f docker-compose.dev.yml up -d
```

#### 3. Run Migrations

```bash
uv run alembic upgrade head
```

#### 4. Seed Database

```bash
# Default (50 bots)
uv run python -m scripts.seed

# Custom options
uv run python -m scripts.seed --users 10 --no-clean
```

#### 5. Run the Server

```bash
uv run uvicorn app.main:app --reload
```

Access at `http://localhost:8000`.

## Running Tests

The project includes integration tests using `pytest` and `asyncio`.

1. Ensure the development database is running (docker-compose.dev.yml).
2. Run tests:

```bash
uv run pytest
```

## Maintenance

Stop and remove containers (keep data):

```bash
# For Dev
docker-compose -f docker-compose.dev.yml down

# For Prod
docker-compose -f docker-compose.prod.yml down
```

Stop and remove everything (delete data):

```bash
# For Dev
docker-compose -f docker-compose.dev.yml down -v

# For Prod
docker-compose -f docker-compose.prod.yml down -v
```