from sqlmodel import Session, SQLModel, create_engine

from app import config

config.DATA_DIR.mkdir(parents=True, exist_ok=True)
config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(config.DB_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
