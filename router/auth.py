from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from database import sessionLocal
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from models import Users
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter()

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
OAuth2_barear = OAuth2PasswordBearer(tokenUrl="/auth/login")

SECRET_KEY = "562de2311ff38d4b0543891bada2dfd931e8547071a0b25aa7f87c43ef1b4f43"
REFRESH_SECRET_KEY = "798ab2311ff38d4b0543891bada2dfd931e8547071a0b25aa7f87c43ef1b999" # আলাদা সিক্রেট কি
ALGORITHM = "HS256"


# ---------------- Schema definitions ----------------

class CreateUser(BaseModel):
    email: str
    username: str
    password: str
    role: str
    firstname: str
    lastname: str


class UpdateUser(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    phone_number: Optional[str] = None


class PasswordUpdate(BaseModel):
    old_password: str
    new_password: str


# ---------------- Helper functions ----------------

def authenticate_user(username, password, db):
    user = db.query(Users).filter(Users.username == username).first()
    if user is None:
        return False
    if bcrypt_context.verify(password, user.hashed_password):
        return user
    return False


def generate_access_token(username: str, user_id: int, role: str, expires: timedelta):
    encode = {"sub": username, "id": user_id, "role": role}
    expires_time = datetime.now(timezone.utc) + expires
    encode.update({"exp": expires_time})
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)


def generate_refresh_token(username: str, user_id: int, expires: timedelta):
    encode = {"sub": username, "id": user_id}
    expires_time = datetime.now(timezone.utc) + expires
    encode.update({"exp": expires_time})
    return jwt.encode(encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: Annotated[str, Depends(OAuth2_barear)]):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        role: str = payload.get("role")
        if username is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid credentials"
            )
        return {"username": username, "id": user_id, "role": role}
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Could not validate credentials"
        )


def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()


user_dependency = Annotated[dict, Depends(get_current_user)]
db_dependency = Annotated[Session, Depends(get_db)]


# ---------------- Endpoints ----------------

@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(db: db_dependency, newUser: CreateUser):
    existing_user = (
        db.query(Users)
        .filter((Users.email == newUser.email) | (Users.username == newUser.username))
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists",
        )

    user_model = Users(
        email=newUser.email,
        username=newUser.username,
        firstname=newUser.firstname,
        lastname=newUser.lastname,
        role=newUser.role,
        hashed_password=bcrypt_context.hash(newUser.password),
    )

    db.add(user_model)
    db.commit()

    return {"status": "Successful", "message": "User created successfully"}


@router.post("/auth/login")
def login(
    response: Response,
    db: db_dependency, 
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Incorrect username or password"
        )
    
    # 1. Short-Lived Access Token (১৫ মিনিট)
    access_token = generate_access_token(
        user.username, user.id, user.role, timedelta(minutes=15)
    )
    
    # 2. Long-Lived Refresh Token (৭ দিন)
    refresh_token = generate_refresh_token(
        user.username, user.id, timedelta(days=7)
    )

    # 3. HTTP-Only Cookie তে Refresh Token সেট করা
    response.set_cookie(
        key="refreshToken",
        value=refresh_token,
        httponly=True,
        secure=True,     # Production (HTTPS)-এ True রাখতে হবে
        samesite="none", # Cross-origin (React to Render Backend) রিকোয়েস্টের জন্য
        max_age=7 * 24 * 60 * 60  # 7 days in seconds
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/auth/refresh-token")
def refresh_token_endpoint(
    db: db_dependency, 
    refreshToken: Optional[str] = None
):
    # নোট: ফ্রন্টএন্ড থেকে credentials: "include" দিলে কুকি থেকে স্বয়ংক্রিয়ভাবে পাওয়া যাবে
    if not refreshToken:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Refresh token missing"
        )

    try:
        payload = jwt.decode(refreshToken, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        
        if username is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid refresh token"
            )

        user = db.query(Users).filter(Users.id == user_id).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="User not found"
            )

        # নতুন Access Token ইস্যু
        new_access_token = generate_access_token(
            user.username, user.id, user.role, timedelta(minutes=15)
        )

        return {"access_token": new_access_token, "token_type": "bearer"}

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid or expired refresh token"
        )


@router.post("/auth/logout")
def logout(response: Response):
    # কুকি রিমুভ করে দেওয়া
    response.delete_cookie(key="refreshToken")
    return {"message": "Logged out successfully"}


@router.put("/updateuser")
def update_user(user_update: UpdateUser, user: user_dependency, db: db_dependency):
    user_model = db.query(Users).filter(Users.id == user.get("id")).first()

    if user_model is None:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(user_model, key, value)

    db.add(user_model)
    db.commit()

    return {"message": "User updated successfully", "updated_fields": update_data}


@router.put("/changepassword")
def change_password(
    update_password: PasswordUpdate, user: user_dependency, db: db_dependency
):
    user_model = db.query(Users).filter(Users.id == user.get("id")).first()
    if user_model is None:
        raise HTTPException(status_code=401, detail="User not found")

    if not bcrypt_context.verify(update_password.old_password, user_model.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect old password")

    user_model.hashed_password = bcrypt_context.hash(update_password.new_password)

    db.add(user_model)
    db.commit()

    return {"message": "Password changed successfully"}