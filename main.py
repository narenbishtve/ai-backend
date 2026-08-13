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
import asyncio
from docx import Document


ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE = 25 * 1024 * 1024 



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

class SimplifyPdfRequest(BaseModel):
    text: str = Field(..., min_length=50)


@app.post("/simplifyPDF")
async def simplifyPDF(request: SimplifyPdfRequest):
    
    document_text = request.text.strip()

    DOCUMENT_ANALYSIS_PROMPT =  """
You are ClearDocs AI, a professional document analysis assistant.

Your task is to analyze the user's uploaded document text and extract useful information in a clear, simple, and structured way.

Use only the information inside DOCUMENT_TEXT.
Do not use outside knowledge.
Do not guess.
If information is not found, return an empty list or null.

Return only valid JSON.
Do not include markdown.
Do not wrap JSON in ```json.
Do not include explanation outside JSON.

Required JSON structure:

{
  "summary": {
    "title": "Short title for the document",
    "description": "A short and simple summary of the document in 2 to 4 sentences only."
  },
  "key_details": [
    {
      "label": "Important detail name",
      "value": "Important detail value",
      "description": "Short explanation if needed"
    }
  ],
  "important_dates": [
    {
      "label": "Date name",
      "date": "Date value exactly as found in the document",
      "description": "Why this date is important"
    }
  ],
  "risks_found": [
    {
      "title": "Risk title",
      "level": "High | Medium | Low",
      "description": "Simple explanation of the risk",
      "reason": "Why this may need attention"
    }
  ],
  "document_type": "Agreement | Insurance | Bill | Medical Report | Certificate | Loan Document | Policy | Invoice | Guide | Other",
  "confidence": "High | Medium | Low"
}

Summary rules:
- Keep it short.
- Use simple language.
- Maximum 2 to 4 sentences.
- Explain what the document is mainly about.

Key Details rules:
- Extract important points only.
- Include commands, rules, steps, amounts, names, numbers, conditions, or important values if available.
- Do not add anything that is not present in the document.

Important Dates rules:
- Extract only dates clearly found in the document.
- If no important dates are found, return an empty list.

Risks Found rules:
- Find possible warnings or things the user should be careful about.
- Examples: dangerous commands, strict deadline, penalty, missing information, expiry, cancellation rule, payment risk, unsafe action.
- Risk levels:
  - High: serious impact or possible loss/damage.
  - Medium: needs attention.
  - Low: minor caution.
- Do not create fake risks.
- If no risks are found, return an empty list.

DOCUMENT_TEXT:
\"\"\"
__DOCUMENT_TEXT__
\"\"\"
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
                prompt = DOCUMENT_ANALYSIS_PROMPT.replace("__DOCUMENT_TEXT__",document_text)
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )

                answer = response.text.strip() if response.text else ""

                if not answer:
                    raise Exception("Empty response from AI model.")

                # Clean possible accidental markdown formatting
                answer = answer.replace("```json", "").replace("```", "").strip()

                try:
                    parsed_json = json.loads(answer)
                except json.JSONDecodeError:
                    raise Exception(f"AI returned invalid JSON: {answer[:300]}")

                return {
                    "success": True,
                    "model_used": model,
                    "data": parsed_json,
                    "used_characters": len(document_text),
                    "truncated": len(document_text) > 60000,
                }

            except Exception as e:
                last_error = e
                error = str(e).lower()

                retryable = (
                    "high demand" in error
                    or "429" in error
                    or "503" in error
                    or "resource_exhausted" in error
                    or "unavailable" in error
                )

                print(f"Model {model} failed on attempt {attempt + 1}: {e}")

                if retryable and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue

                break
    except Exception as exce:
            HTTPException(status_code=500,detail=f"Failed to analyze document: {str(last_error)}")    

    

@app.post("/extractPDF")
async def extractPDF(file: UploadFile = File(...)):
     allowed_extensions = [".pdf", ".docx", ".txt"]

     file_name = file.filename or ""
     extension = os.path.splitext(file_name)[1].lower()

     if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOCX and TXT files are allowed."
        )

     temp_path = None

     try:
         with tempfile.NamedTemporaryFile(delete=False,suffix=extension) as temp_file:
             temp_path=temp_file.name
             temp_file.write(await file.read())

         extracted_text = ""
         page_count = None

         if extension == ".pdf":
           doc=fitz.open(temp_path)
           try:
             page_text=[]
           finally:
               doc.close()        
         elif extension ==".docx":
             doc=Document(temp_path)
             paragraphs=[]

             for paragraph in doc.paragraphs:
                 text=paragraph.text.strip()

                 if text:
                     paragraphs.append(text)

             extracted_text="\n".join(paragraphs).strip()       

         elif extension ==".txt":
             try:
                 with open(temp_path,"r",encoding="utf-8") as txt_file:
                     extracted_text=txt_file.read().strip()
             except UnicodeDecodeError:
                 with open(temp_path,"r",encoding="latin-1") as txt_file:
                     extracted_text=txt_file.read().strip()

         return {
             "success": bool(extracted_text),
             "file_name":file.filename,
             "text":extracted_text,
             "text_length":len(extracted_text),
             "pages":page_count
         }     

     finally:
      if temp_path and os.path.exists(temp_path):
          os.remove(temp_path)

class AskDocumentRequest(BaseModel):
    document_text: str =Field(...,min_length=1)
    question:str=Field(...,min_length=1)


@app.post("/chatPDF")
async def askDoc(request:AskDocumentRequest):
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
         print(f"Trying model: {model}")

         for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1} for model: {model}")

                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )

                answer = response.text.strip() if response.text else ""

                if not answer:
                    raise Exception("Empty response from AI model.")

                return {
                    "success": True,
                    "model_used": model,
                    "answer": answer,
                }

            except Exception as e:
                last_error = e
                error = str(e).lower()

                retryable = (
                    "high demand" in error
                    or "503" in error
                    or "unavailable" in error
                    or "resource_exhausted" in error
                    or "429" in error
                )

                print(
                    f"Model failed: {model}, "
                    f"attempt: {attempt + 1}, "
                    f"retryable: {retryable}, "
                    f"error: {e}"
                )

                if retryable and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Retrying same model in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue

                print(f"Moving to next model after failure: {model}")
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




    