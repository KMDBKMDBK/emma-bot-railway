import firebase_admin
from firebase_admin import credentials, firestore
from api_key_manager import FIREBASE_CREDENTIALS_JSON
import base64
import json
import logging

# Инициализация Firebase
try:
    cred_dict = json.loads(base64.b64decode(FIREBASE_CREDENTIALS_JSON).decode('utf-8'))
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.AsyncClient()
    logging.info("Firebase успешно инициализирован")
except Exception as e:
    logging.error(f"Ошибка инициализации Firebase: {e}")
    raise

async def save_user_data(user_id: int, data: dict, premium_data: dict = None):
    try:
        user_id_str = str(user_id)
        if not user_id_str.isdigit():
            logging.debug(f"Пропуск нечислового user_id: {user_id_str}")
            return
        doc_ref = db.collection("users").document(user_id_str)
        await doc_ref.set(data, merge=True)
        if premium_data:
            await doc_ref.set(premium_data, merge=True)
        logging.info(f"Данные сохранены для user_id: {user_id_str}")
    except Exception as e:
        logging.error(f"Ошибка сохранения данных для user_id {user_id}: {e}")

async def get_user_data(user_id: int) -> dict:
    try:
        user_id_str = str(user_id)
        if not user_id_str.isdigit():
            logging.debug(f"Пропуск нечислового user_id: {user_id_str}")
            return {}
        doc_ref = db.collection("users").document(user_id_str)
        doc = await doc_ref.get()
        return doc.to_dict() or {}
    except Exception as e:
        logging.error(f"Ошибка получения данных для user_id {user_id}: {e}")
        return {}

async def save_message(message_id: str, user_id: str, text: str):
    try:
        if not user_id.isdigit():
            logging.debug(f"Пропуск нечислового user_id: {user_id}")
            return
        doc_ref = db.collection("messages").document(message_id)
        await doc_ref.set({
            "user_id": user_id,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        logging.info(f"Сообщение сохранено: {message_id}")
    except Exception as e:
        logging.error(f"Ошибка сохранения сообщения {message_id}: {e}")

async def get_user_history(user_id: int) -> list:
    try:
        user_id_str = str(user_id)
        if not user_id_str.isdigit():
            logging.debug(f"Пропуск нечислового user_id: {user_id_str}")
            return []
        query = db.collection("messages").where("user_id", "==", user_id_str).order_by("timestamp").limit(20)
        docs = await query.get()
        history = [{"role": "user", "content": doc.to_dict().get("text", "")} for doc in docs]
        logging.info(f"История загружена для user_id: {user_id_str}, {len(history)} сообщений")
        return history
    except Exception as e:
        logging.error(f"Ошибка получения истории для user_id {user_id}: {e}")
        return []