# Library API

Учебный проект: REST API библиотеки (FastAPI + SQLAlchemy), на котором отрабатываем тестирование.

## Запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Документация API: http://127.0.0.1:8000/docs

## Тесты

```powershell
pytest
```
