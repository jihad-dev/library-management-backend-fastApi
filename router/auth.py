from fastapi import APIRouter, HTTPException, status
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session
from typing import Annotated, Optional
from database import sessionLocal
from pydantic import BaseModel
from models import Users
from passlib.context import CryptContext
from datetime import timedelta, datetime, timezone
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt

router = APIRouter()
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
OAuth2_barear = OAuth2PasswordBearer(tokenUrl="/auth/login")
SECRET_KEY = "562de2311ff38d4b0543891bada2dfd931e8547071a0b25aa7f87c43ef1b4f43"
ALGORITHM = "HS256"


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


def authenticate_user(username, password, db):
    user = db.query(Users).filter(Users.username == username).first()
    if user is None:
        return False
    if bcrypt_context.verify(password, user.hashed_password):
        return user

    return False


def generate_access_token(username: str, user_id: str, role: str, expires: timedelta):
    encode = {"sub": username, "id": user_id, "role": role}
    expires = datetime.now(timezone.utc) + expires
    encode.update({"exp": expires})
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: Annotated[str, Depends(OAuth2_barear)]):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        role: str = payload.get("role")
        if username is None or user_id is None:
            raise HTTPException(status_code=404, detail="user not found!")
        return {"username": username, "id": user_id, "role": role}
    except:
        raise HTTPException(status_code=404, detail="user not found!")


def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()


user_dependency = Annotated[dict, Depends(get_current_user)]
db_dependency = Annotated[Session, Depends(get_db)]


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(db: db_dependency, newUser: CreateUser):
    # 1. Check if user already exists
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

    # 2. Hash password and include ALL model fields
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
    db: db_dependency, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        return "Failed Authentication"
    token = generate_access_token(
        user.username, user.id, user.role, timedelta(minutes=30)
    )
    return {"access_token": token, "token_type": "bearer"}


@router.put("/updateuser")
def update_user(user_update: UpdateUser, user: user_dependency, db: db_dependency):
    # 1. Check authentication status
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed Authentication!"
        )

    # 2. Fetch user from database
    user_model = db.query(Users).filter(Users.id == user.get("id")).first()

    # 3. Check if user record exists in database
    if user_model is None:
        raise HTTPException(status_code=404, detail="User not found")

    # 4. Extract only updated fields
    update_data = user_update.model_dump(exclude_unset=True)

    # 5. Apply update attributes to the SQLAlchemy model
    for key, value in update_data.items():
        setattr(user_model, key, value)

    # 6. Save changes to DB
    db.add(user_model)
    db.commit()

    return {"message": "User updated successfully", "updated_fields": update_data}


@router.put("/changepassword")
def change_password(
    update_password: PasswordUpdate, user: user_dependency, db: db_dependency
):
    # 1. Check authentication status
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed Authentication!"
        )

    # 2. Fetch user model from database
    user = db.query(Users).filter(Users.id == user.get("id")).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Failed Authentication!")

    # 3. Verify current password
    if not bcrypt_context.verify(update_password.old_password, user.hash_password):
        raise HTTPException(status_code=400, detail="Incorrect old password")

    # 4. Hash and update new password
    user.hash_password = bcrypt_context.hash(update_password.new_password)

    # 5. Commit changes
    db.add(user)
    db.commit()

    # 6. Return safe response (do NOT return the raw user model)
    return {"message": "Password changed successfully"}
