from fastapi import APIRouter, HTTPException, status
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session
from typing import Annotated, Optional
from database import sessionLocal
from pydantic import BaseModel, Field
from models import  Books, Reservations, IssueRecord
from datetime import timedelta, datetime
from router.auth import get_current_user

router = APIRouter()


class CreateBook(BaseModel):
    title: str
    author: str
    description: str
    category: str
    price: float = 0.0
    total_copies: int = Field(default=1)
    cover_image: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------
# UPDATE BOOK (বইয়ের তথ্য আপডেট করার জন্য)
# ---------------------------------------------------------
class UpdateBook(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    total_copies: Optional[int] = None
    cover_image: Optional[str] = None


class IssuBook(BaseModel):
    user_id: int
    book_id: int


def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()


DAILY_FINE_RATE = 20

user_dependency = Annotated[dict, Depends(get_current_user)]
db_dependency = Annotated[Session, Depends(get_db)]


# Updated route decorator path (removes double /admin)
@router.post("/create_book", status_code=status.HTTP_201_CREATED)
def create_book(user: user_dependency, db: db_dependency, new_book: CreateBook):
    # Missing or invalid token
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Valid token, but incorrect permissions
    if user.get("role") != "librarian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Librarian access required.",
        )

    book_model = Books(**new_book.model_dump(), available_copies=new_book.total_copies)

    db.add(book_model)
    db.commit()
    db.refresh(book_model)

    return {"message": "Book created successfully", "book_id": book_model.id}


@router.put("/update_book/{book_id}", status_code=status.HTTP_200_OK)
def update_book(
    book_id: int, book_update: UpdateBook, user: user_dependency, db: db_dependency
):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.get("role") != "librarian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Librarian access required.",
        )

    book_model = db.query(Books).filter(Books.id == book_id).first()
    if book_model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
        )

    update_data = book_update.model_dump(exclude_unset=True)

    # total_copies পরিবর্তন হলে available_copies অ্যাডজাস্ট করা
    if "total_copies" in update_data:
        copies_difference = update_data["total_copies"] - book_model.total_copies
        book_model.available_copies += copies_difference

        # যদি নতুন total_copies ইতোমধ্যে ইস্যু করা কপির চেয়ে কম হয়
        if book_model.available_copies < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Total copies cannot be less than already issued copies.",
            )

    for key, value in update_data.items():
        setattr(book_model, key, value)

    db.add(book_model)
    db.commit()
    db.refresh(book_model)

    return {"message": "Book updated successfully", "book_id": book_model.id}


# ---------------------------------------------------------
# DELETE BOOK (বই মুছে ফেলার জন্য)
# ---------------------------------------------------------
@router.delete("/delete_book/{book_id}", status_code=status.HTTP_200_OK)
def delete_book(book_id: int, user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.get("role") != "librarian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Librarian access required.",
        )

    book_model = db.query(Books).filter(Books.id == book_id).first()
    if book_model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
        )

    db.delete(book_model)
    db.commit()

    return {"message": f"Book with ID {book_id} deleted successfully"}


@router.post("/create_issue", status_code=status.HTTP_201_CREATED)
def create_issue(user: user_dependency, db: db_dependency, issue_request: IssuBook):
    # ১. ইউজার ও রোল ভ্যালিডেশন
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    if user.get("role") != "librarian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Librarian access required.",
        )

    # ২. বই অস্তিত্বশীল কিনা এবং স্টক আছে কিনা চেক
    book = db.query(Books).filter(Books.id == issue_request.book_id).first()
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book Not Found!",
        )

    if book.available_copies <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No available copies left for this book!",
        )

    # ৩. ইস্যু ও ডিউ ডেট গণনা
    loan_days = 14
    current_time = datetime.now()
    due_date = current_time + timedelta(days=loan_days)

    # ৪. ইস্যু মডেল অবজেক্ট তৈরি
    issue_model = IssueRecord(
        book_id=issue_request.book_id,
        user_id=issue_request.user_id,
        issue_date=current_time,
        due_date=due_date,
        status="issued",
    )

    # ৫. বইয়ের স্টক ১ টি কমানো
    book.available_copies -= 1

    # ৬. ইউজার যদি আগে রিজার্ভ করে থাকে তবে তা আপডেট করা
    reservation = (
        db.query(Reservations)
        .filter(
            Reservations.book_id == issue_request.book_id,
            Reservations.user_id == issue_request.user_id,
            Reservations.status == "pending",
        )
        .first()
    )

    if reservation:
        reservation.status = "approved"

    # ৭. ডাটাবেজে তথ্য সংরক্ষণ
    db.add(issue_model)
    db.commit()
    db.refresh(issue_model)

    return {"message": "Book Issued successfully", "issue_id": issue_model.id}


@router.post("/return_book/{issue_id}", status_code=status.HTTP_200_OK)
def return_book(issue_id: int, user: user_dependency, db: db_dependency):
    # ১. ইউজার ও লাইব্রেরিয়ান ভূমিকা ভ্যালিডেশন
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    if user.get("role") != "librarian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Librarian access required.",
        )

    # ২. ইস্যু রেকর্ড খোঁজা
    issue_record = (
        db.query(IssueRecord)
        .filter(IssueRecord.id == issue_id, IssueRecord.status == "issued")
        .first()
    )

    if issue_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active issue record not found or book already returned.",
        )

    # ৩. সংশ্লিষ্ট বইয়ের তথ্য খোঁজা
    book = db.query(Books).filter(Books.id == issue_record.book_id).first()
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated book not found.",
        )

    # ৪. রিটার্ন ডেট এবং বিলম্ব ফি (Fine) গণনা
    return_time = datetime.now()
    issue_record.return_date = return_time
    issue_record.status = "returned"

    # যদি ফেরত দেওয়ার তারিখ Due Date পার হয়ে যায়
    if return_time > issue_record.due_date:
        overdue_days = (return_time - issue_record.due_date).days
        if overdue_days > 0:
            issue_record.fine_amount = overdue_days * DAILY_FINE_RATE

    # ৫. বইয়ের স্টক ১ বাড়ানো (Available Copies)
    book.available_copies += 1

    # ৬. ডাটাবেজে আপডেট সেভ করা
    db.add(issue_record)
    db.add(book)
    db.commit()
    db.refresh(issue_record)

    return {
        "message": "Book returned successfully",
        "issue_id": issue_record.id,
        "fine_amount": issue_record.fine_amount,
        "fine_paid": issue_record.fine_paid,
    }

    # ---------------------------------------------------------


# PAY FINE (ইউজারের জরিমানা পরিশোধ চিহ্নিত করা)
# ---------------------------------------------------------
@router.put("/pay_fine/{issue_id}", status_code=status.HTTP_200_OK)
def pay_fine(issue_id: int, user: user_dependency, db: db_dependency):
    # ১. ইউজার ভ্যালিডেশন এবং লাইব্রেরিয়ান পারমিশন চেক
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.get("role") != "librarian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Librarian access required.",
        )

    # ২. ইস্যু রেকর্ডটি ডাটাবেজে আছে কিনা খোঁজা
    issue_record = db.query(IssueRecord).filter(IssueRecord.id == issue_id).first()

    if issue_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue record not found.",
        )

    # ৩. জরিমানা আছে কিনা তা চেক করা
    if issue_record.fine_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="There is no fine due for this record.",
        )

    # ৪. ইতোমধ্যে পরিশোধ করা হয়ে গেছে কিনা তা চেক করা
    if issue_record.fine_paid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fine is already paid for this record.",
        )

    # ৫. জরিমানা পরিশোধিত চিহ্নিত করা
    issue_record.fine_paid = True

    # ৬. ডাটাবেজে সেভ করা
    db.add(issue_record)
    db.commit()
    db.refresh(issue_record)

    return {
        "message": "Fine paid successfully",
        "issue_id": issue_record.id,
        "fine_amount": issue_record.fine_amount,
        "fine_paid": issue_record.fine_paid,
    }
