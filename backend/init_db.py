from sqlalchemy import inspect

from backend.database import engine
from backend.models import Base


def initialize_database():
    """Create tables defined by the SQLAlchemy models."""

    print("Creating database tables...")

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print("\nDatabase tables created or verified successfully!")
    print(f"Database: {engine.url.database}")
    print(f"Total tables: {len(tables)}")

    for table in tables:
        print(f" - {table}")


if __name__ == "__main__":
    try:
        initialize_database()
    except Exception as error:
        print(f"Database initialization failed: {error}")
        raise