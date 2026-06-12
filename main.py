from fastapi import FastAPI
import firebase_admin
from firebase_admin import credentials, firestore
import requests
from google import genai
import os
import json
from dotenv import load_dotenv
import time
from fastapi.middleware.cors import CORSMiddleware

app=FastAPI()
origins=["https://remember-dee35.web.app/","http://localhost:64793/"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

firebase_json = os.getenv("FIREBASE_CREDENTIALS")
if firebase_json:
    cred = credentials.Certificate(json.loads(firebase_json))
else:
    cred = credentials.Certificate("rememberFirebase.json")

#cred=credentials.Certificate("rememberFirebase.json")
firebase_admin.initialize_app(cred)

db=firestore.client()
load_dotenv()

client = genai.Client(
    api_key=os.getenv("GOOGLE_API_KEY")
)

@app.get("/")
def home(): return {"message":"API is working fine"}

@app.get("/notes")
def getNotes():
    notest_ref=db.collection("decisions")
    docs=notest_ref.stream()
    notes=[]

    for note in docs:
        data=note.to_dict()
        notes.append({"reason":data['why'],"title":data['title']}) 

    return {"notes":notes,
            "count": len(notes)
            }    
""" @app.get("/commits")
def getCommitMessages():
    url="https://api.github.com/repos/QantumLoyalty/qantum-apps/commits?sha=dev&per_page=100&page=1"
    response=requests.get(url)
    commits_data=response.json()
    commits=[]
    for item in commits_data:
        commits.append({
            "author":item["commit"]["author"]["name"],
            "message":item["commit"]["message"],
            "date":item["commit"]["author"]["date"],
        })
    return {"branch":"dev","commits":commits,"size":len(commits)}    
  """

def fetchCommitMessages():
    url="https://api.github.com/repos/QantumLoyalty/qantum-apps/commits?sha=dev&per_page=100&page=1"
    response=requests.get(url)
    commits_data=response.json()
    commits=[]
    for item in commits_data:
        commits.append({
            "author":item["commit"]["author"]["name"],
            "message":item["commit"]["message"],
            "date":item["commit"]["author"]["date"],
        })

    return commits    


@app.get("/sync-commits")
def syncCommitMessages():
    commitMessages=fetchCommitMessages()
    batch=db.batch()
    for msg in commitMessages:
        doc_ref=db.collection("commits").document(msg["date"])
        batch.set(doc_ref,msg)
    
    batch.commit()    
  
    return {"message": "Data saved successfully!"}



PROMPT_TEMPLATE = """
You are an anniversary notification message generator.

Your task is to convert the user’s life event input into a warm, concise, notification-style message.

Input examples:

* "I started my job today."
* "I purchased my first car."
* "I completed my master's degree on this day."
* "I graduated on that day."

Instructions:

1. Identify the event type, event date, and milestone count.
2. Calculate how many years have passed from the event date to today.
3. Generate a short, friendly notification message.
4. Keep the tone celebratory, personal, and professional.
5. Use natural phrasing such as:
   * "On this day, you started your first job."
   * "It's your car anniversary today."
   * "Today marks an anniversary since you completed your master's degree."
   * "You graduated today. What a milestone!"

Output format:
Return only the final notification message.

User input:
{user_input}
"""

@app.post("/generate-notification-message")
def generateNotificationMessage(message:str):
    return {"message": getMessage(message)}

def getMessage(message:str) -> str:
    models = [
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.5-flash"]
    max_retries = 3
    prompt=PROMPT_TEMPLATE.format(user_input=message)
    for model in models:
        for attempt in range(max_retries):
            try:
              response=client.models.generate_content(model=model,contents=prompt)
              return response.text.strip()
            except Exception as e:
                error =str(e).lower()
                retryable=("high demand" in error
                    or "429" in error
                    or "503" in error
                    or "resource_exhausted" in error
                    or "unavailable" in error)
                if retryable and attempt<max_retries-1:
                    wait_time = 2 ** attempt  # 1, 2, 4 seconds
                    print(
                        f"Model {model} busy. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                    continue
                print(f"Model {model} failed: {e}")
                break
        return ("Today marks a special milestone. Congratulations on your anniversary! 🎉" )




    
    
    




    