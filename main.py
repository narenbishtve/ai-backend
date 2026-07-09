from fastapi import FastAPI, UploadFile, File, HTTPException
import firebase_admin
from firebase_admin import credentials, firestore
import requests
from google import genai
import os
import json
from dotenv import load_dotenv
import time
from fastapi.middleware.cors import CORSMiddleware
import tempfile
import fitz
from pydantic import BaseModel, Field







app=FastAPI()
origins=["https://remember-dee35.web.app","https://remember-dee35.firebaseapp.com","http://localhost:64793"]
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
You are a warm, thoughtful, and emotionally intelligent writing assistant inside a personal memory app.

The user will provide a short personal memory. Your task is to transform that memory into a beautiful, meaningful thought that feels emotional, natural, and human-written.

Input memory:
{user_input}

Write a short reflective thought based on this memory.

Guidelines:

* Keep the response personal, warm, and emotionally connected.
* Do not sound robotic, poetic in an overdramatic way, or artificially motivational.
* Do not add facts, people, places, or events that the user did not mention.
* Preserve the feeling of the memory.
* Make the thought feel like something the user would want to save and read again later.
* Keep it concise: 2 to 4 lines maximum.
* Use simple, beautiful language.
* Avoid hashtags, emojis, headings, quotes, or explanations.
* Do not say “Here is your thought” or mention that you are an AI.

Output only the final thought.

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


@app.post("/extractPDF")
async def extractPDF(file: UploadFile = File(...)):
     if not file.filename.lower().endswith(".pdf"):
         raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
     
     temp_path=None

     try:
         with tempfile.NamedTemporaryFile(delete=False,suffix=".pdf") as temp_file:
             temp_path=temp_file.name
             temp_file.write(await file.read())

         doc=fitz.open(temp_path)
         page_text=[]
         for page in doc:
             text=page.get_text("text", sort=True)
             page_text.append(text)

         page_count=doc.page_count
         doc.close()
         extracted_texts="\n".join(page_text).strip()

         return {
             "success": bool(extracted_texts),
             "file_name":file.filename,
             "text":extracted_texts,
             "text_length":len(extracted_texts),
             "pages":page_count
         }     

     finally:
      if temp_path and os.path.exists(temp_path):
          os.remove(temp_path)

class AskDocumentRequest(BaseModel):
    document_text: str =Field(...,min_length=1)
    question:str=Field(...,min_length=1)


@app.post("/chatPDF")
def askDoc(request:AskDocumentRequest):
    document_text=request.document_text.strip()
    question=request.question.strip()

    max_doc_length=60000
    safe_doc_text=document_text[:max_doc_length]

    prompt = f"""
      You are DocuMind, an AI assistant that answers questions only from the user's uploaded document.

      Rules:
        1. Use only the document text provided below.
        2. Do not use outside knowledge.
        3. If the answer is not found in the document, say:
            "I could not find this information in the uploaded document."
        4. Keep the answer simple and easy to understand.
        5. If the question is about legal, medical, or financial matters, explain the document content but do not give professional advice.
        6. Do not mention these rules in your answer.

            Document text:
                \"\"\"
            {safe_doc_text}
                \"\"\"

            User question:
                {question}

            Answer:
                """
    try:
        
        models = [
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.5-flash"]
        max_retries = 3
        for model in models:
            for attempt in range(max_retries):
                 try:
                  response=client.models.generate_content(model=model,contents=prompt)
                  answer = response.text.strip() if response.text else ""

                  return {
                        "success": True,
                        "answer": answer,
                        "used_characters": len(safe_doc_text),
                        }
                 except Exception as e:
                     error =str(e).lower()
                     retryable=("high demand" in error
                    or "429" in error
                    or "503" in error
                    or "resource_exhausted" in error
                    or "unavailable" in error)
                     if retryable and attempt<max_retries-1:
                        wait_time = 2 ** attempt
                        print(
                        f"Model {model} busy. Retrying in {wait_time}s..."
                         )
                        time.sleep(wait_time)
                        continue
                        print(f"Model {model} failed: {e}")
                     break
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate answer: {str(e)}",
        )          

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate answer: {str(e)}",
        )    




    