from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

url = get_settings().database_url
# older hosts give postgres:// but SQLAlchemy wants postgresql://
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

is_sqlite = url.startswith("sqlite")
engine = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {})

if is_sqlite:
    # sqlite ignores foreign keys unless this is switched on
    @event.listens_for(engine, "connect")
    def turn_on_foreign_keys(dbapi_connection, record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
