from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from glass.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _sync_url(url: str) -> str:
    """Ensure the URL uses psycopg (v3) for synchronous SQLAlchemy connections."""
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return url.replace("://", "+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(settings.database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_sync_url(settings.database_url), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
