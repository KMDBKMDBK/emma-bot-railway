import logging
import firebase_admin
from firebase_admin import credentials, firestore
import os
import base64
import json
from handlers import user_data

logger = logging.getLogger(__name__)

def init_firebase():
    firebase_credentials = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if firebase_credentials:
        try:
            cred_json = base64.b64decode(firebase_credentials).decode()
            cred = credentials.Certificate(json.loads(cred_json))
            firebase_admin.initialize_app(cred)
            logger.info("Firebase инициализирован успешно (base64)")
        except Exception as e:
            logger.warning(f"Firebase не инициализирован из base64: {e}")
    else:
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase инициализирован успешно (локальный путь)")
        else:
            logger.warning("Firebase не инициализирован (проверь FIREBASE_CREDENTIALS_PATH или FIREBASE_CREDENTIALS_JSON)")
    try:
        db = firestore.client()
        docs = db.collection("users").stream()
        for doc in docs:
            try:
                user_id_int = int(doc.id)
                user_data[user_id_int] = doc.to_dict()
                logger.info(f"Загружены данные пользователя {user_id_int} из Firestore")
            except ValueError:
                logger.warning(f"Пропуск невалидного user_id: {doc.id} (не число)")
        logger.info("Все user_data загружены из Firestore")
    except Exception as e:
        logger.error(f"Ошибка загрузки user_data из Firestore: {e}")

async def save_user_data(user_id: int, data: dict):
    try:
        db = firestore.client()
        db.collection("users").document(str(user_id)).set(data, merge=True)
        logger.info(f"Сохранены user_data для {user_id} в Firestore")
    except Exception as e:
        logger.error(f"Ошибка сохранения user_data: {e}")

async def save_message_to_firestore(user_id: str, text: str, message_id: str):
    try:
        db = firestore.client()
        doc_ref = db.collection("messages").document(message_id)
        doc_ref.set({
            "user_id": user_id,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
        logger.info(f"Сообщение сохранено в Firestore с ID: {message_id}")
    except Exception as e:
        logger.error(f"Ошибка сохранения в Firestore: {e}")