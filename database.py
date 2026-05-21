# database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://neondb_owner:npg_VHoy3w7zpXxN@ep-solitary-hall-alcyc7uk.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require"

# SQLite үшін check_same_thread=False міндетті түрде керек (FastAPI көп ағынды болғандықтан)
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Деректер қорының сессиясын алуға арналған Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
