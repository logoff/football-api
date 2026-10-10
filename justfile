set dotenv-load := true

# List recipes
default:
    @just --list

# Install dependencies into .venv
install:
    uv sync

# Start the stack (api + postgres) in the background
up:
    docker compose up -d --build --wait

# Stop the stack
down:
    docker compose down

# Follow container logs
logs:
    docker compose logs -f

# Apply database migrations
migrate:
    uv run alembic upgrade head

# Pull sources and reconcile them into the database
sync: migrate
    uv run python -m football_api.sync

# Sync one competition by Wikidata QID, e.g. `just sync-competition Q324867 --verify`
sync-competition qid *flags: migrate
    uv run python -m football_api.sync --competition {{qid}} {{flags}}

# Open a psql shell on the stack's database
psql:
    docker compose exec postgres psql -U football football

# Run the test suite (needs `just up` for db-marked tests)
test *args:
    uv run pytest {{args}}

# Strict type check
typecheck:
    uv run pyright
