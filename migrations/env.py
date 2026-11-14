
from logging.config import fileConfig

from alembic import context

from backend.database import engine
from backend.models import Base


# Get Alembic configuration
config = context.config


# Configure logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Connect SQLAlchemy models to Alembic
target_metadata = Base.metadata


# ============================================================
# OFFLINE MIGRATIONS
# Generates SQL without directly connecting to the database
# ============================================================

def run_migrations_offline():

    url = engine.url.render_as_string(
        hide_password=True
    )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True
    )

    with context.begin_transaction():
        context.run_migrations()


# ============================================================
# ONLINE MIGRATIONS
# Connects directly to PostgreSQL
# ============================================================

def run_migrations_online():

    with engine.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True
        )

        with context.begin_transaction():
            context.run_migrations()


# Choose migration mode
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
