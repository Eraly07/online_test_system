# main.py
from fastapi import FastAPI, Depends, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict
import bcrypt  # Тікелей bcrypt қолданамыз

import models
from database import engine, get_db

# Деректер қоры кестелерін жасау
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- ҚҰПИЯ СӨЗДІ БАСҚАРУ ФУНКЦИЯЛАРЫ ---
def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)


# Көмекші функция: Cookie арқылы пайдаланушыны анықтау
def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == int(user_id)).first()

class TestSubmission(BaseModel):
    answers: Dict[int, str]


# --- АУТЕНТИФИКАЦИЯ РОУТТАРЫ ---

@app.get("/", response_class=HTMLResponse)
def index(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"user": None})

@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        return templates.TemplateResponse(request, "register.html", {
            "error": "Бұл пайдаланушы аты бос емес!", "user": None
        })
    
    # Жаңа қауіпсіз хэштеу функциясы
    hashed_password = hash_password(password)
    new_user = models.User(username=username, password=hashed_password)
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"user": None})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.username == username).first()
    # Жаңа тексеру функциясы
    if not user or not verify_password(password, user.password):
        return templates.TemplateResponse(request, "login.html", {
            "error": "Пайдаланушы аты немесе құпия сөз қате!", "user": None
        })
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id))
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("user_id")
    return response


# --- ПАНЕЛЬ ЖӘНЕ ТЕСТ CRUD РОУТТАРЫ ---

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    tests = db.query(models.Test).all()
    results = db.query(models.Result).filter(models.Result.user_id == user.id).order_by(models.Result.created_at.desc()).all()
    
    # 🌟 ЖАҢА: Ең үздік 5 нәтижені (Рейтингті) базадан алу
    top_results = db.query(models.Result).order_by(models.Result.percentage.desc()).limit(5).all()
    
    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "tests": tests,
        "results": results,
        "top_results": top_results  # Шаблонға жібереміз
    })

@app.get("/test/create", response_class=HTMLResponse)
def create_test_page(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "create_test.html", {"user": user})

@app.post("/test/create")
async def create_test(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form_data = await request.form()
    title = form_data.get("title")
    description = form_data.get("description")
    total_q = int(form_data.get("total_questions_count", 0))
    
    new_test = models.Test(title=title, description=description, creator_id=user.id)
    db.add(new_test)
    db.commit()
    db.refresh(new_test)
    
    for i in range(1, total_q + 1):
        q_text = form_data.get(f"q_text_{i}")
        if not q_text: 
            continue
            
        question = models.Question(
            test_id=new_test.id,
            text=q_text,
            option_a=form_data.get(f"q_a_{i}"),
            option_b=form_data.get(f"q_b_{i}"),
            option_c=form_data.get(f"q_c_{i}"),
            option_d=form_data.get(f"q_d_{i}"),
            correct_option=form_data.get(f"q_correct_{i}")
        )
        db.add(question)
    
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/test/{test_id}/delete")
def delete_test(
    test_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    test = db.query(models.Test).filter(models.Test.id == test_id).first()
    if test and test.creator_id == user.id:
        db.delete(test)
        db.commit()
        
    return RedirectResponse(url="/dashboard", status_code=303)


# --- ТЕСТ ОРЫНДАУ ЖӘНЕ БАҒАЛАУ РОУТТАРЫ ---

@app.get("/test/{test_id}", response_class=HTMLResponse)
def pass_test_page(
    test_id: int, 
    request: Request, 
    db: Session = Depends(get_db), 
    user=Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
        
    test = db.query(models.Test).filter(models.Test.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Тест табылмады")
        
    return templates.TemplateResponse(request, "pass_test.html", {
        "user": user, 
        "test": test
    })

@app.post("/test/{test_id}/submit")
def submit_test(
    test_id: int,
    submission: TestSubmission,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="Авторизациядан өтпеген")
        
    test = db.query(models.Test).filter(models.Test.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Тест табылмады")

    correct_count = 0
    total_questions = len(test.questions)
    
    if total_questions == 0:
        return {"score": 0, "total_questions": 0, "percentage": 0.0}

    for question in test.questions:
        user_answer = submission.answers.get(str(question.id)) or submission.answers.get(question.id)
        if user_answer and user_answer.upper() == question.correct_option.upper():
            correct_count += 1

    percentage = (correct_count / total_questions) * 100

    result = models.Result(
        user_id=user.id,
        test_id=test.id,
        score=correct_count,
        total_questions=total_questions,
        percentage=percentage
    )
    db.add(result)
    db.commit()

    return {
        "score": correct_count,
        "total_questions": total_questions,
        "percentage": percentage
    }