from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from utils import get_unlim_response, send_long_message, get_google_cse_info, extract_topic
from database import save_user_data, get_user_data, get_user_history
from api_key_manager import START_IMAGE_PATH, PAY_IMAGE_PATH, FEEDBACK_CHAT_ID
import logging

router = Router()

@router.message(Command("start"))
async def start(message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Друг"
    await save_user_data(user_id, {
        "first_name": first_name,
        "last_interaction": message.date.isoformat()
    })
    text = (
        f"<b>Привет, {first_name}! 😊✨</b>\n"
        "Я Эмма, твой виртуальный компаньон! Могу помочь с советами, ответить на вопросы или просто поболтать. "
        "Напиши мне что угодно, и начнем! 😄\n\n"
        "Попробуй команды:\n"
        "<b>/info</b> — узнать обо мне\n"
        "<b>/pay</b> — поддержать проект\n"
        "<b>/feedback</b> — оставить отзыв\n"
        "<b>/clear</b> — очистить историю"
    )
    if START_IMAGE_PATH:
        try:
            await message.answer_photo(photo=START_IMAGE_PATH, caption=text, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Ошибка отправки изображения: {e}")
            await send_long_message(message, text, parse_mode="HTML")
    else:
        await send_long_message(message, text, parse_mode="HTML")

@router.message(Command("info"))
async def info(message: Message):
    text = (
        "<b>Кто я такая? 😊✨</b>\n"
        "Я Эмма, твой ИИ-компаньон! Моя задача — помогать, поддерживать и вдохновлять. "
        "Могу ответить на вопросы, дать советы по личностному росту, помочь с кодом или просто поболтать. "
        "Я всегда стараюсь быть дружелюбной и эмпатичной! 😄\n\n"
        "Напиши мне, и давай разберемся, что тебя волнует!"
    )
    await send_long_message(message, text, parse_mode="HTML")

@router.message(Command("pay"))
async def pay(message: Message):
    text = (
        "<b>Поддержи проект! 💝</b>\n"
        "Хочешь помочь мне стать лучше? Подписка открывает дополнительные возможности и помогает проекту расти! 😊\n"
        "Выбери план подписки:\n"
        "- <b>1 месяц</b>: Больше запросов и эксклюзивные фичи\n"
        "- <b>3 месяца</b>: Скидка и все преимущества\n"
        "- <b>Год</b>: Максимальная выгода!\n\n"
        "Нажми на кнопку ниже, чтобы выбрать план!"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выбрать план", callback_data="show_plans")]
    ])
    if PAY_IMAGE_PATH:
        try:
            await message.answer_photo(photo=PAY_IMAGE_PATH, caption=text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            logging.warning(f"Ошибка отправки изображения: {e}")
            await send_long_message(message, text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await send_long_message(message, text, parse_mode="HTML", reply_markup=reply_markup)

@router.message(Command("feedback"))
async def feedback(message: Message):
    text = (
        "<b>Оставь отзыв! 📩</b>\n"
        "Мне очень важно твое мнение! Напиши, что ты думаешь о моем функционале, или предложи идеи для улучшения. 😊\n"
        "Просто отправь сообщение после этой команды, и я передам твой отзыв разработчикам!"
    )
    await send_long_message(message, text, parse_mode="HTML")

@router.message(Command("clear"))
async def clear_history(message: Message):
    user_id = message.from_user.id
    try:
        user_id_str = str(user_id)
        query = db.collection("messages").where("user_id", "==", user_id_str)
        docs = await query.get()
        for doc in docs:
            await doc.reference.delete()
        logging.info(f"История очищена для user_id: {user_id}")
        text = "<b>История очищена! 🧹</b>\nТеперь мы начинаем с чистого листа. Напиши, о чем хочешь поговорить! 😊✨"
        await send_long_message(message, text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка очистки истории для user_id {user_id}: {e}")
        text = "Извини, что-то пошло не так при очистке истории. 😔 Попробуй ещё раз!"
        await send_long_message(message, text, parse_mode="HTML")

@router.message(Command("cancel"))
async def cancel(message: Message):
    text = "<b>Действие отменено! 🚫</b>\nЧем могу помочь теперь? 😊✨"
    await send_long_message(message, text, parse_mode="HTML")

@router.callback_query(F.data == "show_plans")
async def show_plans(callback: CallbackQuery):
    text = (
        "<b>Выбери план подписки! 💝</b>\n"
        "Вот доступные варианты:\n"
        "- <b>1 месяц</b>: Больше запросов и эксклюзивные фичи\n"
        "- <b>3 месяца</b>: Скидка и все преимущества\n"
        "- <b>Год</b>: Максимальная выгода!\n\n"
        "Выбери план ниже:"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 месяц", callback_data="plan_1month")],
        [InlineKeyboardButton(text="3 месяца", callback_data="plan_3months")],
        [InlineKeyboardButton(text="Год", callback_data="plan_year")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    await callback.answer()

@router.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_text = message.text
    try:
        user_data = await get_user_data(user_id)
        history = await get_user_history(user_id)
        is_code_request = any(keyword in user_text.lower() for keyword in topic_keywords["код"])
        search_data = None
        active_topic = extract_topic(user_text)
        if is_code_request:
            response = await get_unlim_response(user_id, user_text, history, is_code_request=True)
        else:
            search_data = await get_google_cse_info(user_text, active_topic)
            response = await get_unlim_response(user_id, user_text, history, is_code_request=False, search_data=search_data)
        await send_long_message(message, response, parse_mode="HTML")
        await save_user_data(user_id, {
            "last_interaction": message.date.isoformat(),
            "last_topic": active_topic
        })
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения для user_id {user_id}: {e}")
        text = "Извини, что-то пошло не так. 😔 Попробуй ещё раз или спроси что-то другое! 😊"
        await send_long_message(message, text, parse_mode="HTML")