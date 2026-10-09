import os
from datetime import timedelta

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import models
import schemas
import database
import auth
from database import engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Nadin Task Manager")

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    return JSONResponse(
        status_code=400,
        content={
            "message": "یک خطای غیرمنتظره رخ داد. لطفاً ورودی‌های خود را بررسی کنید.",
            "details": str(exc)
        }
    )

@app.get("/")
def read_root():
    return {"message": "سرور با موفقیت در حال اجراست!"}

@app.post("/register", response_model=schemas.UserResponse, tags=["Authentication"])
def register_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        username=user.username,
        email=user.email,
        phone_number=user.phone_number,
        password_hash=hashed_password
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, 
            detail="این نام کاربری، ایمیل یا شماره تلفن قبلاً در سیستم ثبت شده است."
        )

@app.post("/login", response_model=schemas.Token, tags=["Authentication"])
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نام کاربری یا رمز عبور اشتباه است",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=schemas.UserResponse, tags=["Users"])
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

@app.post("/users/profile-image", tags=["Users"])
def upload_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    file_path = os.path.join(UPLOAD_DIR, f"profile_{current_user.id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())
        
    current_user.profile_image = file_path
    db.commit()
    
    return {
        "message": "تصویر پروفایل با موفقیت آپلود شد", 
        "profile_image": file_path
    }

@app.post("/tasks/", response_model=schemas.TaskResponse, tags=["Tasks"])
def create_task(
    title: str = Form(...),
    description: str = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    file_url = None
    if file:
        file_path = os.path.join(UPLOAD_DIR, f"{current_user.id}_{file.filename}")
        with open(file_path, "wb") as buffer:
            buffer.write(file.file.read())
        file_url = file_path

    new_task = models.Task(
        title=title,
        description=description,
        attachment_url=file_url,
        user_id=current_user.id
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

@app.get("/tasks/", tags=["Tasks"])
def get_all_tasks(
    skip: int = 0, 
    limit: int = 10, 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    query = db.query(models.Task)
    
    if current_user.role != models.RoleEnum.admin:
        query = query.filter(models.Task.user_id == current_user.id)
        
    tasks = query.offset(skip).limit(limit).all()
    return tasks

@app.put("/tasks/{task_id}", response_model=schemas.TaskResponse, tags=["Tasks"])
def update_task(
    task_id: int, 
    task_update: schemas.TaskUpdate, 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="تسک یافت نشد")
        
    if current_user.role != models.RoleEnum.admin and task.user_id != current_user.id:
         raise HTTPException(status_code=403, detail="شما اجازه ویرایش این تسک را ندارید")

    task.title = task_update.title
    task.description = task_update.description
    db.commit()
    db.refresh(task)
    return task

@app.delete("/tasks/{task_id}", tags=["Tasks"])
def delete_task(
    task_id: int, 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="تسک یافت نشد")
        
    if current_user.role != models.RoleEnum.admin and task.user_id != current_user.id:
         raise HTTPException(status_code=403, detail="شما اجازه حذف این تسک را ندارید")

    if task.attachment_url and os.path.exists(task.attachment_url):
        os.remove(task.attachment_url)

    db.delete(task)
    db.commit()
    return {"message": "تسک با موفقیت حذف شد"}

@app.get("/download/{task_id}", tags=["Tasks"])
def download_task_attachment(
    task_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task or not task.attachment_url:
        raise HTTPException(status_code=404, detail="فایلی برای این تسک یافت نشد")
        
    if current_user.role != models.RoleEnum.admin and task.user_id != current_user.id:
         raise HTTPException(status_code=403, detail="شما دسترسی دانلود این فایل را ندارید")
         
    return FileResponse(path=task.attachment_url, filename=os.path.basename(task.attachment_url))