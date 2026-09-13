import datetime
from typing import Annotated, Literal, Optional

from database import engine, sessionLocal
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import models
from models import Books, IssueRecord, Reservations
from pydantic import BaseModel, Field
from router import admin, auth
from router.auth import get_current_user
from sqlalchemy.orm import Session

app = FastAPI()

# ---------------------------------------------------------
# CORS কনফিগারেশন (সঠিকভাবে আপডেট করা হয়েছে)
# ---------------------------------------------------------
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    # ভবিষ্যতে Vercel/Netlify বা অন্য কোথাও হোস্ট করলে সেই URL-ও নিচে যোগ করবেন:
    # "https://your-frontend.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # নির্দিষ্ট origins এলাউ করা (কুকির জন্য '*' ব্যবহার করা যাবে না)
    allow_credentials=True,      # HTTP-Only Refresh Token Cookie এর জন্য আবশ্যক
    allow_methods=["*"],
    allow_headers=["*"],
)

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


# ---------------------------------------------------------
# PUBLIC ENDPOINTS (লগইন ছাড়া সবাই দেখতে পারবে)
# ---------------------------------------------------------
@app.get("/books/all")
def get_all_books(db: db_dependency):
    """
    সব বইয়ের তালিকা দেখার জন্য লগইন বাধ্যতামূলক নয়। 
    এটি 401 Unauthorized এবং ইনস্ট্যান্ট লগআউট হওয়া বন্ধ করবে।
    """
    books = db.query(Books).all()
    return books


@app.get("/books/{book_id}")
def get_specific_book(book_id: int, db: db_dependency):
    book = db.query(Books).filter(Books.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="Book Not Found")
    return book


# ---------------------------------------------------------
# PROTECTED ENDPOINTS (লগইন করা বাধ্যতামূলক)
# ---------------------------------------------------------
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
        status_code=200, content={"message": "Reservation Cancelled Successfully"}
    )


@app.get("/reserve/my")
def my_reservation(user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication Failed"
        )

    reservations = (
        db.query(Reservations).filter(Reservations.user_id == user.get("id")).all()
    )

    return reservations


@app.get("/my_issued_books", status_code=status.HTTP_200_OK)
def get_my_issued_books(user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user_id = user.get("id")

    issued_records = (
        db.query(IssueRecord)
        .filter(IssueRecord.user_id == user_id, IssueRecord.status == 'issued')
        .all()
    )
    return issued_records