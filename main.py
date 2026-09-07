from typing import Annotated, Literal, Optional
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import datetime
from database import engine, sessionLocal
import models
from models import Books, Reservations,IssueRecord
from router import auth, admin
from router.auth import get_current_user

app = FastAPI()
app.include_router(auth.router)
app.include_router(admin.router, prefix="/admin")
models.Base.metadata.create_all(bind=engine)


# Database dependency
def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]


@app.get("/")
def home():
    return "Hello Next Level Developer💀 Welcome To Library Management Project!"


@app.get("/books/all")
def get_all_books(user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication Failed")
    books = db.query(Books).all()
    return books


@app.get("/books/{book_id}")
def get_specefic_books(user: user_dependency, db: db_dependency, book_id: int):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication Failed")
    book = db.query(Books).filter(Books.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="Book Not Found")
    return book


@app.post("/reserve/{book_id}")
def reserve_book(user: user_dependency, db: db_dependency, book_id: int):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication Failed")
    book = db.query(Books).filter(Books.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="Book Not Found")
    reservations_model = Reservations(
        book_id=book_id, user_id=user.get("id"), status="pending"
    )
    db.add(reservations_model)
    db.commit()
    db.refresh()
    return JSONResponse(
        status_code=201, content={"message": "Book Reserved Successfully"}
    )


@app.delete("/reserve/cancel/{reservation_id}")
def cancel_reservation(user: user_dependency, db: db_dependency, reservation_id: int):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication Failed")
    reservation = (
        db.query(Reservations).filter(Reservations.id == reservation_id).first()
    )
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation Not Found")
    reservation.status = "cancelled"
    db.commit()
    return JSONResponse(
        status_code=201, content={"message": "Reservation Cancelled Successfully"}
    )


@app.get("/reserve/my")
def my_reservation(user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication Failed"
        )

    # Fetch all reservations for this specific user
    reservations = (
        db.query(Reservations).filter(Reservations.user_id == user.get("id")).all()
    )

    # Check if the list is empty
    if not reservations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No reservations found"
        )

    return reservations


# ---------------------------------------------------------
# MY ISSUED BOOKS (লগইন করা ইউজারের নিজস্ব ইস্যু করা বইয়ের তালিকা)
# ---------------------------------------------------------
@app.get("/my_issued_books", status_code=status.HTTP_200_OK)
def get_my_issued_books(user: user_dependency, db: db_dependency):
    # ১. ইউজার ভ্যালিডেশন
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            
        )

    user_id = user.get("id")

    # ২. এই ইউজারের সব ইস্যু রেকর্ড এবং সাথে বইয়ের তথ্য বের করা
    issued_records = (
        db.query(IssueRecord)
        .filter(IssueRecord.user_id == user_id, IssueRecord.status == 'issued')
        .all()
    )
    return issued_records
