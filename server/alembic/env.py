import os
from contextlib import suppress
from logging.config import fileConfig

from sqlmodel import SQLModel

from alembic import context

config = context.config
if config.config_file_name:
    with suppress(KeyError):
        fileConfig(config.config_file_name)
database_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
target_metadata = SQLModel.metadata


def run_migrations_offline():
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(
        {**config.get_section(config.config_ini_section, {}), "sqlalchemy.url": database_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
