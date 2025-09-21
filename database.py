import firebase_admin
from firebase_admin import credentials, firestore
import os
import base64
import json
import logging

firebase_credentials = os.getenv("FIREBASE_CREDENTIALS_JSON")
if firebase_credentials:
    try:
        cred_json = base64.b64decode(firebase_credentials).decode()
        cred = credentials.Certificate(json.loads(cred_json))
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logging.info("Firebase инициализирован успешно (base64)")
    except Exception as e:
        db = None
        logging.warning(f"Firebase не инициализирован из base64: {e}")
else:
    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logging.info("Firebase инициализирован успешно (локальный путь)")
    else:
        db = None
        logging.warning("Firebase не инициализирован (проверь FIREBASE_CREDENTIALS_PATH или FIREBASE_CREDENTIALS_JSON)")

async def save_user_data(user_id: int, data: dict, premium_data: dict = None):
    if db:
        try:
            doc_ref = db.collection('users').document(str(user_id))
            update_data = data.copy()
            if premium_data:
                update_data.update(premium_data)
            doc_ref.set(update_data, merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

async def save_message(message_id: str, user_id: str, text: str):
    if db:
        try:
            doc_ref = db.collection('messages').document(message_id)
            doc_ref.set({
                'user_id': user_id,
                'text': text,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
            logging.info(f"Сообщение сохранено в Firestore с ID: {message_id}")
        except Exception as e:
            logging.error(f"Ошибка сохранения в Firestore: {e}")