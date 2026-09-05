from datetime import datetime
from database import Base
from sqlalchemy import Column, Boolean, Integer, Float, String, ForeignKey, DateTime


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    firstname = Column(String)
    lastname = Column(String)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    role = Column(String)


class Books(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    author = Column(String, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)
    price = Column(Float, default=0.0)
    total_copies = Column(Integer, default=5)
    available_copies = Column(Integer, default=3)
    cover_image = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class Reservations(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey="books.id")
    user_id = Column(Integer, ForeignKey="users.id")
    reservation_date = Column(DateTime, default=datetime.now)
    status = Column(String, default="pending")
