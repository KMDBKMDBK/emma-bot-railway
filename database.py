import logging
import os
import base64
import json
import firebase_admin
from firebase_admin import credentials, firestore
from handlers import user_data

db = None

def init_firebase():
    global db
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

async def save_user_data(user_id: int, data: dict):
    if db:
        try:
            db.collection('users').document(str(user_id)).set(data, merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

async def load_user_data():
    if db:
        try:
            users_ref = db.collection('users').stream()
            async for user in users_ref:
                user_id = int(user.id)
                user_data[user_id] = user.to_dict()
                logging.info(f"Загружены user_data для {user_id} из Firestore")
        except Exception as e:
            logging.error(f"Ошибка загрузки user_data: {e}")