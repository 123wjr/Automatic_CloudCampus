import sqlalchemy.event
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@sqlalchemy.event.listens_for(engine, "connect")
def _enable_wal(dbapi_connection, connection_record):
    dbapi_connection.execute("PRAGMA journal_mode=WAL")


def _run_migrations():
    with engine.connect() as conn:
        for col, col_def in [
            ("trade_no", "VARCHAR(64) DEFAULT ''"),
            ("context_json", "TEXT DEFAULT ''"),
        ]:
            try:
                conn.exec_driver_sql(
                    f"ALTER TABLE payment_orders ADD COLUMN {col} {col_def}"
                )
            except Exception:
                pass
        try:
            conn.exec_driver_sql("COMMIT")
        except Exception:
            pass


_run_migrations()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

