
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base
SQLALCHEMY_DATABASE_URL = "sqlite:///./library.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)

sessionLocal = sessionmaker(autoflush=False, autocommit=False, bind=engine)
Base = declarative_base()