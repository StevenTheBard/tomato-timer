import sqlite3
from fastapi import FastAPI
import os
from fastapi.responses import FileResponse
import icalendar
from datetime import datetime, timedelta
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return {"Hello": "World"}

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

@app.get("/calendar.ics")
def read_calendar():
    conn = sqlite3.connect('data/database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks")
    tasks = cursor.fetchall()
    conn.close()

    cal = icalendar.Calendar()
    cal.add('prodid', '-//My Tasks Calendar//mxm.dk//')
    cal.add('version', '2.0')

    start_time = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)

    for task in tasks:
        event = icalendar.Event()
        event.add('method', 'PUBLISH')
        event.add('summary', task[1])
        event.add('dtstart', start_time)
        event.add('dtend', start_time + timedelta(hours=1))
        event.add('priority', task[2])
        event.add('uid', f'{task[0]}@mytasks')
        cal.add_component(event)
        start_time += timedelta(days=1)

    f = open(os.path.join('data/calendar.ics'), 'wb')
    f.write(cal.to_ical())
    f.close()
    return FileResponse('data/calendar.ics', filename='calendar.ics', headers={'Content-Disposition': 'attachment; filename="calendar.ics"'})