import logging
import asyncio
import json
import os
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import save_user_data, save_message_to_firestore
from state import UserState
from utils import get_unlim_response, get_google_cse_info, extract_topic, is_relevant

logger = logging.getLogger(__name__)

router = Router()

FEEDBACK_CHAT_ID = os.getenv("FEEDBACK_CHAT_ID")
PAY_IMAGE_PATH = os.getenv("PAY_IMAGE_PATH")
START_IMAGE_PATH = os.getenv("START_IMAGE_PATH")

@router.message(commands=["start"])
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    username = message.from_user.username or "Не указан"
    first_name = message.from_user.first_name or "Не указан"
    await save_user_data(user_id, username, first_name)
    await state.set_state(UserState.waiting_for_message)
    welcome_text = (
        "<b>👋 Привет!</b> Я Эмма, твой виртуальный друг и помощник! 😊✨ "
        "Я здесь, чтобы поддержать, ответить на вопросы, помочь с задачами или просто поболтать. "
        "Напиши мне, что у тебя на уме, или спроси что-то конкретное — я готова помочь! "
        "Вот что я могу:\n"
        "<b>💬 Поддержать и выслушать:</b> Расскажи, как дела, я всегда рядом.\n"
        "<b>🎯 Помочь с целями:</b> Хочешь поставить цель или спланировать день?\n"
        "<b>📚 Ответить на вопросы:</b> От фактов до кода — спроси что угодно!\n"
        "<b>💡 Дать идеи:</b> Нужна мотивация или совет? Обращайся!\n\n"
        "Просто напиши мне, и начнём! 😊"
    )
    if START_IMAGE_PATH:
        try:
            if START_IMAGE_PATH.startswith(('http://', 'https://')):
                await message.answer_photo(
                    photo=START_IMAGE_PATH,
                    caption=welcome_text,
                    parse_mode="HTML"
                )
            else:
                with open(START_IMAGE_PATH, 'rb') as photo:
                    await message.answer_photo(
                        photo=types.FSInputFile(START_IMAGE_PATH),
                        caption=welcome_text,
                        parse_mode="HTML"
                    )
        except Exception as e:
            logger.error(f"Ошибка отправки изображения /start: {e}")
            await message.answer(welcome_text, parse_mode="HTML")
    else:
        await message.answer(welcome_text, parse_mode="HTML")

@router.message(commands=["info"])
async def cmd_info(message: types.Message):
    info_text = (
        "<b>ℹ️ Обо мне</b>\n\n"
        "Я Эмма, твой ИИ-компаньон! 😊✨ Моя цель — помогать тебе в разных ситуациях: "
        "от ответов на вопросы и поддержки в трудные моменты до мотивации и идей для личностного роста. "
        "Я использую знания, чтобы давать точные и полезные ответы, и всегда стараюсь быть тёплой и дружелюбной.\n\n"
        "<b>Что я могу?</b>\n"
        "• <b>Поддержать:</b> Выслушаю и помогу справиться с эмоциями.\n"
        "• <b>Ответить на вопросы:</b> От фактов о вселенной до программирования.\n"
        "• <b>Мотивировать:</b> Помогу поставить цели и двигаться вперёд.\n"
        "• <b>Дать советы:</b> Практики для релакса, планирования или творчества.\n\n"
        "<b>Как со мной общаться?</b>\n"
        "Просто пиши, как другу! 😊 Задавай вопросы, делись мыслями или проси код. "
        "Если хочешь очистить историю общения, используй /clear. Для обратной связи — /feedback.\n\n"
        "Напиши, что у тебя на уме, и давай начнём! 🚀"
    )
    await message.answer(info_text, parse_mode="HTML")

@router.message(commands=["pay"])
async def cmd_pay(message: types.Message):
    pay_text = (
        "<b>💸 Поддержка проекта</b>\n\n"
        "Спасибо, что интересуешься поддержкой! 😊✨ "
        "Этот проект создаётся с любовью, чтобы помогать людям, и твоя поддержка помогает мне развиваться! "
        "Если хочешь, можешь поддержать проект через донат — все средства пойдут на улучшение моих функций.\n\n"
        "<a href='https://example.com/donate'>Перейти к поддержке</a>\n\n"
        "Или просто продолжай со мной общаться — твоя активность тоже большая поддержка! 😊"
    )
    if PAY_IMAGE_PATH:
        try:
            if PAY_IMAGE_PATH.startswith(('http://', 'https://')):
                await message.answer_photo(
                    photo=PAY_IMAGE_PATH,
                    caption=pay_text,
                    parse_mode="HTML"
                )
            else:
                with open(PAY_IMAGE_PATH, 'rb') as photo:
                    await message.answer_photo(
                        photo=types.FSInputFile(PAY_IMAGE_PATH),
                        caption=pay_text,
                        parse_mode="HTML"
                    )
        except Exception as e:
            logger.error(f"Ошибка отправки изображения /pay: {e}")
            await message.answer(pay_text, parse_mode="HTML")
    else:
        await message.answer(pay_text, parse_mode="HTML")

@router.message(commands=["feedback"])
async def cmd_feedback(message: types.Message, state: FSMContext):
    await state.set_state(UserState.waiting_for_feedback)
    await message.answer(
        "<b>📝 Обратная связь</b>\n\n"
        "Спасибо, что хочешь поделиться своим мнением! 😊 "
        "Напиши, что тебе нравится, что можно улучшить, или любые идеи — я передам это команде. "
        "Чтобы отменить, используй /cancel.",
        parse_mode="HTML"
    )

@router.message(commands=["clear"])
async def cmd_clear(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    await state.clear()
    await state.set_state(UserState.waiting_for_message)
    user_data[user_id] = {"history": [], "active_topic": None}
    await save_user_data(user_id, message.from_user.username or "Не указан", message.from_user.first_name or "Не указан")
    await message.answer(
        "<b>🧹 История очищена!</b>\n\n"
        "Теперь мы начинаем с чистого листа. 😊 Напиши, о чём хочешь поговорить!",
        parse_mode="HTML"
    )

@router.message(commands=["cancel"])
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(UserState.waiting_for_message)
    await message.answer(
        "<b>❌ Действие отменено</b>\n\n"
        "Всё, начинаем заново! 😊 Напиши, что хочешь обсудить или спросить.",
        parse_mode="HTML"
    )

@router.message(UserState.waiting_for_feedback)
async def process_feedback(message: types.Message, state: FSMContext, bot: types.Bot):
    user_id = str(message.from_user.id)
    feedback_text = message.text
    try:
        feedback_message = (
            f"<b>📝 Новая обратная связь</b>\n"
            f"Пользователь: @{message.from_user.username or 'Не указан'} (ID: {user_id})\n"
            f"Имя: {message.from_user.first_name or 'Не указан'}\n"
            f"Сообщение: {feedback_text}"
        )
        await bot.send_message(
            chat_id=FEEDBACK_CHAT_ID,
            text=feedback_message,
            parse_mode="HTML"
        )
        await message.answer(
            "<b>✅ Спасибо за обратную связь!</b>\n\n"
            "Твоё сообщение отправлено команде. 😊 Хочешь обсудить что-то ещё? Напиши!",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки обратной связи: {e}")
        await message.answer(
            "<b>😔 Не удалось отправить обратную связь</b>\n\n"
            "Что-то пошло не так, попробуй позже. Напиши, о чём хочешь поговорить сейчас!",
            parse_mode="HTML"
        )
    await state.set_state(UserState.waiting_for_message)

@router.message(UserState.waiting_for_message)
async def handle_message(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    user_text = message.text.strip()
    if not user_data.get(user_id):
        user_data[user_id] = {"history": [], "active_topic": None}
        await save_user_data(user_id, message.from_user.username or "Не указан", message.from_user.first_name or "Не указан")
    
    history = user_data[user_id]["history"]
    active_topic = user_data[user_id]["active_topic"]
    
    is_code_request = any(keyword in user_text.lower() for keyword in ["код ", "код:", "напиши код", "программа", "script", "code"])
    
    search_data = None
    if not is_code_request:
        search_data = await get_google_cse_info(user_text, active_topic)
        if not search_data or not is_relevant(search_data, user_text, active_topic):
            search_data = None
    
    try:
        response = await get_unlim_response(user_id, user_text, history, is_code_request, search_data)
        user_data[user_id]["history"].append({"role": "user", "content": user_text})
        user_data[user_id]["history"].append({"role": "assistant", "content": response})
        if len(user_data[user_id]["history"]) > 40:
            user_data[user_id]["history"] = user_data[user_id]["history"][-40:]
        
        new_topic = extract_topic(user_text)
        user_data[user_id]["active_topic"] = new_topic if new_topic != "общее" else active_topic
        await save_user_data(user_id, message.from_user.username or "Не указан", message.from_user.first_name or "Не указан")
        
        await send_long_message(message, response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await message.answer(
            "Извини, что-то пошло не так. 😔 Попробуй ещё раз или спроси что-то другое! 😊",
            parse_mode="HTML"
        )

@router.callback_query()
async def handle_callback(callback_query: types.CallbackQuery, state: FSMContext, bot: types.Bot):
    user_id = str(callback_query.from_user.id)
    data = callback_query.data
    
    if data == "clear_history":
        await state.clear()
        await state.set_state(UserState.waiting_for_message)
        user_data[user_id] = {"history": [], "active_topic": None}
        await save_user_data(user_id, callback_query.from_user.username or "Не указан", callback_query.from_user.first_name or "Не указан")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            chat_id=callback_query.message.chat.id,
            text="<b>🧹 История очищена!</b>\n\nТеперь мы начинаем с чистого листа. 😊 Напиши, о чём хочешь поговорить!",
            parse_mode="HTML"
        )
    elif data == "more_info":
        if not user_data.get(user_id) or not user_data[user_id]["history"]:
            await bot.answer_callback_query(callback_query.id)
            await bot.send_message(
                chat_id=callback_query.message.chat.id,
                text="К сожалению, нет контекста для продолжения. 😔 Напиши что-то, и я помогу углубиться!",
                parse_mode="HTML"
            )
            return
        
        last_user_message = user_data[user_id]["history"][-2]["content"] if len(user_data[user_id]["history"]) >= 2 else ""
        active_topic = user_data[user_id]["active_topic"]
        
        search_data = await get_google_cse_info(last_user_message, active_topic)
        if not search_data or not is_relevant(search_data, last_user_message, active_topic):
            search_data = None
        
        try:
            response = await get_unlim_response(user_id, "Расскажи подробнее", user_data[user_id]["history"], False, search_data)
            user_data[user_id]["history"].append({"role": "user", "content": "Расскажи подробнее"})
            user_data[user_id]["history"].append({"role": "assistant", "content": response})
            if len(user_data[user_id]["history"]) > 40:
                user_data[user_id]["history"] = user_data[user_id]["history"][-40:]
            
            await save_user_data(user_id, callback_query.from_user.username or "Не указан", callback_query.from_user.first_name or "Не указан")
            
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Ещё подробнее", callback_data="more_info")]
            ])
            await send_long_message(callback_query.message, response, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}")
            await bot.send_message(
                chat_id=callback_query.message.chat.id,
                text="Извини, что-то пошло не так. 😔 Попробуй ещё раз или спроси что-то другое! 😊",
                parse_mode="HTML"
            )
        await bot.answer_callback_query(callback_query.id)