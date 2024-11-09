import sqlite3
from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}

@app.get("/reset")
def reset():
    if not os.path.exists('data'):
        os.mkdir('data')
    if os.path.exists('data/database.db'):
        os.remove('data/database.db')
    conn = sqlite3.connect('data/database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            task TEXT NOT NULL,
            priority INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/tasks/{task_id}")
def read_task(task_id: int):
    conn = sqlite3.connect('data/database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
    task = cursor.fetchone()
    conn.close()
    if task:
        return {"task_id": task_id, "task": task}
    else:
        return {"task_id": task_id, "task": "Task not found"}

@app.post("/tasks")
def create_task(task: str, priority: int):
    conn = sqlite3.connect('data/database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (task, priority) VALUES (?, ?)", (task, priority))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return {"task_id": task_id, "task": task, "priority": priority}

