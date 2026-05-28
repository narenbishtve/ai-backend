from fastapi import FastAPI
import firebase_admin
# from firebase_admin import credentials, firestore
import requests

app=FastAPI()

#cred=credentials.Certificate("rememberFirebase.json")
#firebase_admin.initialize_app(cred)

#db=firestore.client()


@app.get("/")
def home(): return {"message":"API is working fine"}

""" @app.get("/notes")
def getNotes():
    notest_ref=db.collection("decisions")
    docs=notest_ref.stream()
    notes=[]

    for note in docs:
        data=note.to_dict()
        notes.append({"reason":data['why'],"title":data['title']}) """

#    return {"notes":notes,
#            "count": len(notes)
#            }    
@app.get("/commits")
def getCommitMessages():
    url="https://api.github.com/repos/QantumLoyalty/qantum-apps/commits?sha=dev"
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
 

