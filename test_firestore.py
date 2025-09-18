import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv

load_dotenv()
cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Тестовая запись
doc_ref = db.collection('messages').document('test123')
doc_ref.set({
    'user_id': 12345,
    'text': 'Это тестовое сообщение!',
    'timestamp': firestore.SERVER_TIMESTAMP
})

# Чтение записи
doc = doc_ref.get()
if doc.exists:
    print(f"Данные: {doc.to_dict()}")
else:
    print("Документ не найден!")