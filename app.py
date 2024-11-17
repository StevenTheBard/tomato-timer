import sqlite3
from fastapi import FastAPI
import os
from fastapi.responses import FileResponse
import icalendar
from datetime import datetime, timedelta
from fastapi.staticfiles import StaticFiles
import requests
from fastapi import HTTPException
from dotenv import load_dotenv
import re

load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return {"Hello": datetime.now()}

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
        
@app.get("/calendar/events")
def get_events():
    access_token = os.getenv('OUTLOOK_ACCESS_TOKEN')
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is missing")
    url = "https://graph.microsoft.com/v1.0/me/calendarview?startdatetime="+str(datetime.now()-timedelta(days=1))+"&enddatetime="+str(datetime.now()+timedelta(days=8))+"&top=1000"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(status_code=response.status_code, detail=response.json())
    
@app.post("/calendar/event/")
def create_event(summary: str, start_time: datetime, end_time: datetime, priority: int):
    access_token = os.getenv('OUTLOOK_ACCESS_TOKEN')
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is missing")

    url = "https://graph.microsoft.com/v1.0/me/events/"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    event_data = {
        "subject": summary,
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": "UTC"
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": "UTC"
        },
        "importance": "high" if priority == 1 else "normal"
    }

    response = requests.post(url, headers=headers, json=event_data)
    if response.status_code == 201:
        return response.json()
    else:
        raise HTTPException(status_code=response.status_code, detail=response.json())
    
def in_awake_hours(free_start):
    return CONFIG["wake_hours"][0] <= free_start.hour < CONFIG["wake_hours"][1]

def schedule_event(task, busy_times):
    free_start = datetime.now().replace(hour=datetime.now().hour+1, minute=0, second=0, microsecond=0)
    free_end = free_start + timedelta(hours=25)

    global CONFIG
    while any(start < free_end and end > free_start for start, end in busy_times) or not in_awake_hours(free_start):
        free_start += timedelta(minutes=30)
        free_end = free_start + timedelta(minutes=25)
    create_event(task, free_start, free_end, 0)
    busy_times.append((free_start, free_end))
    return busy_times

@app.post("/schedule/")
def upload_calendar():
    events=get_events()
    tasks=get_uncompleted_tasks()
    existing_event_summaries = [event['subject'] for event in events.get('value', [])]
    new_tasks = [task for task in tasks if task["title"] not in existing_event_summaries]
    
    busy_times = [(datetime.fromisoformat(event['start']['dateTime']), datetime.fromisoformat(event['end']['dateTime'])) for event in events.get('value', [])]
    busy_times.sort()
    for task in new_tasks:
        if task.get("checklistItems") and re.search(r'(\d+)h', task["checklistItems"][0]["displayName"]):
            hours=int(task["checklistItems"][0]["displayName"].replace("h", ""))
            for _ in range(2*hours):
                busy_times=schedule_event(task["title"], busy_times)        
        else:
            busy_times=schedule_event(task["title"], busy_times)        
        if busy_times[-1][0] > datetime.now()+timedelta(days=7):
            break
    return {"new_events": [t["title"] for t in  new_tasks]}

def get_all_tasks():
    access_token = os.getenv('OUTLOOK_ACCESS_TOKEN')
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is missing")

    url = "https://graph.microsoft.com/v1.0/me/todo/lists"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        lists = response.json().get('value', [])
        tasks = []
        for todo_list in lists:
            if  re.search(r'(\d+)-',todo_list['displayName']):
                list_id = todo_list['id']
                tasks_url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks"
                tasks_response = requests.get(tasks_url, headers=headers)
                if tasks_response.status_code == 200:
                    tasks.extend(tasks_response.json().get('value', []))
                else:
                    raise HTTPException(status_code=tasks_response.status_code, detail=tasks_response.json())
        return tasks
    else:
        raise HTTPException(status_code=response.status_code, detail=response.json())

@app.get("/todo/")
def get_uncompleted_tasks():
    tasks=get_all_tasks()
    incomplete_tasks = [task for task in tasks if task['status'] != 'completed']
    sorted_tasks = sorted(incomplete_tasks, key=lambda x: x['importance'], reverse=False)
    return sorted_tasks

CONFIG = {"business_hours": [7, 18],"wake_hours": [5,21 ]}

@app.post("/config/")
def save_config(config: dict):
    global CONFIG
    CONFIG = config
    return {"status": "config saved"}

@app.get("/config/")
def get_config():
    global CONFIG
    return CONFIG
