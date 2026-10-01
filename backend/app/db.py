from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

ES_SQLITE = settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if ES_SQLITE else {},
    pool_pre_ping=True,
)

if ES_SQLITE:

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()
        # plano(x): texto sin acentos y en minúsculas, para la búsqueda inteligente
        dbapi_conn.create_function("plano", 1, plano, deterministic=True)


def plano(v):
    import unicodedata

    if v is None:
        return None
    return unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode().lower()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
