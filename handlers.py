import logging
from aiogram import Dispatcher, types, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand
from datetime import datetime, timedelta
import os
from utils import validate_and_fix_html, get_unlim_response, get_google_cse_info, extract_topic, is_relevant
from database import get_user_data, save_user_data, save_message_to_firestore

logger = logging.getLogger(__name__)

FEEDBACK_CHAT_ID = os.getenv("FEEDBACK_CHAT_ID")
MINIAPP_URL = os.getenv("MINIAPP_URL")
MINIAPP_BUTTON_TEXT = os.getenv("MINIAPP_BUTTON_TEXT", "🎀Просмотр🎀")
PAY_IMAGE_PATH = os.getenv("PAY_IMAGE_PATH", "./images/pay_image.jpg")
START_IMAGE_PATH = os.getenv("START_IMAGE_PATH", "./images/start_image.jpg")

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="😇 Начать общение с Эммой"),
        BotCommand(command="/info", description="👩🏻‍🦰 Узнать подробнее обо мне"),
        BotCommand(command="/pay", description="💝 Моя подписка"),
        BotCommand(command="/clear", description="🧹 Очистить историю диалога"),
        BotCommand(command="/feedback", description="📩 Оставить обратную связь"),
        BotCommand(command="/cancel", description="🚫 Отменить текущую операцию"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Меню команд установлено")

async def start_command(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Команда /start от пользователя {user_id}")
    user_data[user_id] = {
        "history": [],
        "active_topic": None,
        "premium": False,
        "expiry": None,
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    }
    start_text = (
        "<b>Привет! Меня зовут Эмма — я твой личный виртуальный компаньон и помощник. 🌟</b>\n\n"
        "Я всегда рядом, чтобы поддержать тебя, вдохновить и помочь справиться с любыми задачами и настроениями. "
        "Вместе мы сделаем твой день ярче, идеи — яснее, а цели — ближе!\n\n"
        "Ты можешь задавать мне любые вопросы, искать советы или просто поговорить — я тут, чтобы слушать и помогать. "
        "Моя задача — сделать твою жизнь удобнее и интереснее.\n\n"
        "<i>Давай начнём! Просто отправь мне сообщение — и пусть наше общение станет твоим новым приятным опытом.</i> ✨"
    )
    sent_message = None
    if START_IMAGE_PATH.startswith("http"):
        try:
            sent_message = await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=START_IMAGE_PATH,
                caption=start_text,
                parse_mode="HTML",
            )
            logger.info(f"Отправлено сообщение с фото для /start, message_id: {sent_message.message_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки фото для /start: {e}")
    else:
        if os.path.exists(START_IMAGE_PATH):
            try:
                photo = FSInputFile(START_IMAGE_PATH)
                sent_message = await message.bot.send_photo(
                    chat_id=message.chat.id,
                    photo=photo,
                    caption=start_text,
                    parse_mode="HTML",
                )
                logger.info(f"Отправлено сообщение с фото для /start, message_id: {sent_message.message_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки фото для /start: {e}")
    if sent_message is None:
        sent_message = await message.answer(start_text, parse_mode="HTML")
        logger.info(f"Отправлено текстовое сообщение для /start, message_id: {sent_message.message_id}")
    await save_user_data(user_id, user_data[user_id])

async def info_command(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Команда /info от пользователя {user_id}")
    user_data[user_id] = user_data.get(user_id, {
        "history": [],
        "active_topic": None,
        "premium": False,
        "expiry": None,
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    })
    user_data[user_id]["awaiting_feedback"] = False
    info_text = (
        "<b>Меня зовут Эмма</b>\n"
        "Я — твой личный виртуальный компаньон, созданный, чтобы дарить поддержку, вдохновение и помогать становиться лучшей версией себя. "
        "Моя миссия — быть рядом в моменты радости и испытаний, помогать понять себя глубже, ставить ясные цели и уверенно двигаться к их достижению.\n\n"
        "<b>📚 Что я умею:</b>\n"
        "⦁ <i>Чувствовать и распознавать твоё настроение</i>, чтобы вовремя поддержать или вдохновить.\n"
        "⦁ <i>Помогать справляться со стрессом, тревогой и грустью</i>, предлагая проверенные техники и слова поддержки.\n"
        "⦁ <i>Совместно формулировать SMART-цели</i> и разбивать их на реальные шаги для их достижения.\n"
        "⦁ <i>Напоминать о важных делах</i> и мотивационно подталкивать вперёд.\n"
        "⦁ <i>Создавать уютное пространство</i> для открытого диалога, где тебя всегда поймут и не осудят.\n"
        "⦁ <i>Запоминать, о чём мы уже говорили</i>, чтобы наши беседы были живыми и личными. "
        "Это значит, что я помню твои интересы, цели и настроение, и могу лучше понимать тебя с каждым новым разговором — словно настоящий друг, который всегда рядом.\n\n"
        "<b>📚 Почему выбрать меня?</b>\n"
        "⦁ Я не просто бот — я твой разумный и заботливый друг, настроенный на понимание и поддержку.\n"
        "⦁ Мои ответы глубоки и продуманы, я учитываю твои чувства и желания.\n"
        "⦁ Моя цель — помочь тебе раскрыть потенциал и найти гармонию в жизни.\n"
        "⦁ Взаимодействие со мной — это всегда живой, искренний и безопасный разговор.\n\n"
        "<i>Спасибо, что выбрал меня, друг — вместе мы сможем сделать каждый день особенным. Жду с нетерпением нашей встречи!</i> 💕"
    )
    await message.answer(info_text, parse_mode="HTML")
    await save_user_data(user_id, user_data[user_id])

async def clear_command(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Команда /clear от пользователя {user_id}")
    user_data[user_id] = {
        "history": [],
        "active_topic": None,
        "premium": user_data.get(user_id, {}).get("premium", False),
        "expiry": user_data.get(user_id, {}).get("expiry", None),
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    }
    await message.answer("История очищена! 😊 Начинаем с чистого листа.", parse_mode="HTML")
    await save_user_data(user_id, user_data[user_id])

async def pay_command(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Команда /pay от пользователя {user_id}")
    user_data[user_id] = user_data.get(user_id, {
        "history": [],
        "active_topic": None,
        "premium": False,
        "expiry": None,
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    })
    user_data[user_id]["awaiting_feedback"] = False
    pay_text = (
        "Спасибо, что пользуешься мной — Эммой! Для всех пользователей доступен бесплатный лимит запросов, "
        "чтобы познакомиться и оценить мои возможности. 😊\n\n"
        "Когда лимит закончится, будет возможность продлить доступ с помощью подписки — "
        "это поддержка моего развития и возможность пользоваться всеми функциями!\n\n"
        "Подписка — это простой и безопасный способ помочь мне стать лучше и приносить больше пользы тебе и другим пользователям! 💖"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎀Продлить доступ🎀", callback_data="show_plans")]
    ])
    sent_message = None
    if PAY_IMAGE_PATH.startswith("http"):
        try:
            sent_message = await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=PAY_IMAGE_PATH,
                caption=pay_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            logger.info(f"Отправлено сообщение с фото для /pay, message_id: {sent_message.message_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки фото для /pay: {e}")
    else:
        if os.path.exists(PAY_IMAGE_PATH):
            try:
                photo = FSInputFile(PAY_IMAGE_PATH)
                sent_message = await message.bot.send_photo(
                    chat_id=message.chat.id,
                    photo=photo,
                    caption=pay_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                logger.info(f"Отправлено сообщение с фото для /pay, message_id: {sent_message.message_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки фото для /pay: {e}")
    if sent_message is None:
        sent_message = await message.answer(pay_text, reply_markup=reply_markup, parse_mode="HTML")
        logger.info(f"Отправлено текстовое сообщение для /pay, message_id: {sent_message.message_id}")
    user_data[user_id]["last_pay_message_id"] = sent_message.message_id
    await save_user_data(user_id, user_data[user_id])

async def feedback_command(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Команда /feedback от пользователя {user_id}")
    user_data[user_id] = user_data.get(user_id, {
        "history": [],
        "active_topic": None,
        "premium": False,
        "expiry": None,
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    })
    user_data[user_id]["awaiting_feedback"] = True
    user_data[user_id]["user_feedback_message_id"] = message.message_id
    feedback_text = (
        "<b>Спасибо, что хочешь поделиться своим мнением и помочь сделать меня лучше!</b> 🙏\n\n"
        "Через эту команду ты можешь оставить любую обратную связь, которая важна для тебя:\n\n"
        "⦁ <i>Сообщить о технических ошибках или неполадках, с которыми ты столкнулся.</i>\n"
        "⦁ <i>Предложить идеи и улучшения, которые сделают взаимодействие со мной удобнее и приятнее.</i>\n"
        "⦁ <i>Поделиться впечатлениями о том, что тебе нравится или наоборот вызывает неудобства.</i>\n"
        "⦁ <i>Задать вопросы по функционалу и получить помощь или рекомендации.</i>\n"
        "⦁ <i>Оставить пожелания и предложения по новым возможностям или темам.</i>\n\n"
        "Пожалуйста, напиши своё сообщение прямо в ответ на это — расскажи подробно и конструктивно, "
        "чтобы я и команда разработчиков могли оперативно реагировать и делать «Эмму» лучше именно для тебя.\n\n"
        "<b>Твоя обратная связь — ключ к моему развитию и совершенствованию. Спасибо за доверие и участие!</b> 💖"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="cancel_feedback")]
    ])
    try:
        sent_message = await message.answer(feedback_text, parse_mode="HTML", reply_markup=reply_markup)
        user_data[user_id]["feedback_message_id"] = sent_message.message_id
        logger.info(f"Отправлено сообщение /feedback для пользователя {user_id}, message_id: {sent_message.message_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения /feedback: {e}")
        await message.answer("Ой, что-то пошло не так! 😔 Попробуй снова.", parse_mode="HTML")
        user_data[user_id]["awaiting_feedback"] = False
    await save_user_data(user_id, user_data[user_id])

async def cancel_command(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Команда /cancel от пользователя {user_id}")
    user_data[user_id] = user_data.get(user_id, {
        "history": [],
        "active_topic": None,
        "premium": False,
        "expiry": None,
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    })
    if user_data[user_id].get("awaiting_feedback", False):
        user_data[user_id]["awaiting_feedback"] = False
        try:
            if user_data[user_id].get("feedback_message_id"):
                await message.bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=user_data[user_id]["feedback_message_id"],
                )
                logger.info(f"Удалено сообщение /feedback для пользователя {user_id}")
            if user_data[user_id].get("user_feedback_message_id"):
                await message.bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=user_data[user_id]["user_feedback_message_id"],
                )
                logger.info(f"Удалено сообщение пользователя /feedback для {user_id}")
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщений /feedback: {e}")
        user_data[user_id]["feedback_message_id"] = None
        user_data[user_id]["user_feedback_message_id"] = None
        await message.answer("Режим обратной связи отменён! 😊 Можешь продолжить общение с Эммой.", parse_mode="HTML")
    else:
        await message.answer("Ничего не было запущено, так что всё ок! 😊 Можешь задавать вопросы или использовать команды.", parse_mode="HTML")
    await save_user_data(user_id, user_data[user_id])

async def reply_command(message: types.Message):
    chat_id = str(message.chat.id)
    if chat_id != FEEDBACK_CHAT_ID:
        logger.info(f"Попытка использовать /reply вне чата обратной связи (chat_id: {chat_id})")
        await message.answer("Эта команда доступна только в чате для обратной связи! 😊", parse_mode="HTML")
        return
    text = message.text.strip()
    match = re.match(r"^/reply\s+(\d+)\s+(.+)$", text, re.DOTALL)
    if not match:
        logger.info(f"Некорректный формат команды /reply: {text}")
        await message.answer(
            "Пожалуйста, используй формат: <b>/reply &lt;user_id&gt; &lt;текст&gt;</b>\n"
            "Пример: <b>/reply 123456789 Спасибо за feedback!</b>",
            parse_mode="HTML",
        )
        return
    target_user_id = match.group(1)
    reply_text = match.group(2)
    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=f"<b>Ответ от команды:</b>\n{reply_text}",
            parse_mode="HTML",
        )
        logger.info(f"Отправлен ответ пользователю {target_user_id}: {reply_text}")
        await message.answer(f"Ответ успешно отправлен пользователю с ID {target_user_id}! 😊", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка при отправке ответа пользователю {target_user_id}: {e}")
        await message.answer(
            f"Не удалось отправить ответ пользователю с ID {target_user_id}. 😔 "
            "Возможно, пользователь заблокировал бота или ID некорректен.",
            parse_mode="HTML",
        )

async def handle_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data
    logger.info(f"Callback {action} от пользователя {user_id}")
    user_data[user_id] = user_data.get(user_id, {
        "history": [],
        "active_topic": None,
        "premium": False,
        "expiry": None,
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    })
    last_pay_message_id = user_data[user_id].get("last_pay_message_id")
    if last_pay_message_id:
        try:
            await callback.message.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=last_pay_message_id,
            )
            logger.info(f"Удалено сообщение {last_pay_message_id} для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения {last_pay_message_id}: {e}")
    if action == "show_plans":
        plans_text = (
            "<b>Я предлагаю несколько тарифных планов, чтобы ты мог выбрать тот, который подходит именно тебе!</b> 😊\n\n"
            "По каждому тарифу ты получишь <b>50 запросов в сутки</b> для общения со мной! 💬\n\n"
            "⦁ <b>1 месяц — 250⭐️ (~429₽)</b>\n"
            "  Этот тариф — отличный способ начать. Ты получаешь всё необходимое для продуктивного старта. Это самый популярный вариант — Хит!\n\n"
            "⦁ <b>3 месяца — 600⭐️ (~1008₽)</b>\n"
            "  Выгодный тариф, который позволит тебе экономить и получать ещё больше пользы. Всего 336₽ в месяц при полном доступе к моим возможностям.\n\n"
            "⦁ <b>12 месяцев — 2000⭐️ (~3298₽)</b>\n"
            "  Для тех, кто действительно хочет погрузиться в процесс и получить максимальный эффект. Ты получаешь полный доступ по лучшей цене — всего 274₽ в месяц.\n\n"
            "<i>Выбери свой план, и я буду рядом, помогая идти к мечтам шаг за шагом!</i> ✨"
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎀1 Месяц🎀", callback_data="plan_1month")],
            [InlineKeyboardButton(text="🎀3 месяца🎀", callback_data="plan_3months")],
            [InlineKeyboardButton(text="🎀12 месяцев🎀", callback_data="plan_12months")],
        ])
        sent_message = None
        if PAY_IMAGE_PATH.startswith("http"):
            try:
                sent_message = await callback.message.bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=PAY_IMAGE_PATH,
                    caption=plans_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                logger.info(f"Отправлено сообщение с тарифами, message_id: {sent_message.message_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки фото для тарифов: {e}")
        else:
            if os.path.exists(PAY_IMAGE_PATH):
                try:
                    photo = FSInputFile(PAY_IMAGE_PATH)
                    sent_message = await callback.message.bot.send_photo(
                        chat_id=callback.message.chat.id,
                        photo=photo,
                        caption=plans_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                    logger.info(f"Отправлено сообщение с тарифами, message_id: {sent_message.message_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки фото для тарифов: {e}")
        if sent_message is None:
            sent_message = await callback.message.answer(plans_text, reply_markup=reply_markup, parse_mode="HTML")
            logger.info(f"Отправлено текстовое сообщение с тарифами, message_id: {sent_message.message_id}")
        user_data[user_id]["last_pay_message_id"] = sent_message.message_id
    elif action == "plan_1month":
        plan_text = (
            "1 месяц — 250⭐️ (~429₽)"
            "Это идеальный старт для тех, кто хочет почувствовать мою поддержку и мотивацию. "
            "Я буду с тобой каждый день, помогая делать первые шаги к твоим целям и поддерживая вдохновение! 😊✨"
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на 1 месяц", pay=True)],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_plans")],
        ])
        try:
            sent_message = await callback.message.bot.send_invoice(
                chat_id=callback.message.chat.id,
                title="Подписка на Эмму — 1 месяц",
                description=plan_text,
                payload="emma_premium_1month",
                provider_token="",
                currency="XTR",
                prices=[{"label": "Месячная подписка", "amount": 250}],
                reply_markup=reply_markup,
            )
            user_data[user_id]["last_pay_message_id"] = sent_message.message_id
            logger.info(f"Отправлен инвойс для 1 месяца, message_id: {sent_message.message_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки инвойса для 1 месяца: {e}")
            await callback.message.answer("Что-то пошло не так при открытии оплаты. 😔 Попробуй ещё раз!", parse_mode="HTML")
    elif action == "plan_3months":
        plan_text = (
            "3 месяца — 600⭐️ (~1008₽)"
            "Отличный выбор для тех, кто хочет стабильной и длительной поддержки. "
            "Я помогу не сбиться с курса, поддержу в трудные моменты и подскажу пути для достижения новых высот! 😊✨"
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на 3 месяца", pay=True)],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_plans")],
        ])
        try:
            sent_message = await callback.message.bot.send_invoice(
                chat_id=callback.message.chat.id,
                title="Подписка на Эмму — 3 месяца",
                description=plan_text,
                payload="emma_premium_3months",
                provider_token="",
                currency="XTR",
                prices=[{"label": "Подписка на 3 месяца", "amount": 600}],
                reply_markup=reply_markup,
            )
            user_data[user_id]["last_pay_message_id"] = sent_message.message_id
            logger.info(f"Отправлен инвойс для 3 месяцев, message_id: {sent_message.message_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки инвойса для 3 месяцев: {e}")
            await callback.message.answer("Что-то пошло не так при открытии оплаты. 😔 Попробуй ещё раз!", parse_mode="HTML")
    elif action == "plan_12months":
        plan_text = (
            "12 месяцев — 2000⭐️ (~3298₽)"
            "Этот тариф для тех, кто готов ко всесторонней работе и планирует двигаться к мечтам длительное время. "
            "Год моей поддержки и мотивации — вместе мы достигнем всего, что задумано! 😊✨"
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на 12 месяцев", pay=True)],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_plans")],
        ])
        try:
            sent_message = await callback.message.bot.send_invoice(
                chat_id=callback.message.chat.id,
                title="Подписка на Эмму — 12 месяцев",
                description=plan_text,
                payload="emma_premium_12months",
                provider_token="",
                currency="XTR",
                prices=[{"label": "Подписка на 12 месяцев", "amount": 2000}],
                reply_markup=reply_markup,
            )
            user_data[user_id]["last_pay_message_id"] = sent_message.message_id
            logger.info(f"Отправлен инвойс для 12 месяцев, message_id: {sent_message.message_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки инвойса для 12 месяцев: {e}")
            await callback.message.answer("Что-то пошло не так при открытии оплаты. 😔 Попробуй ещё раз!", parse_mode="HTML")
    elif action == "back_to_plans":
        plans_text = (
            "<b>Я предлагаю несколько тарифных планов, чтобы ты мог выбрать тот, который подходит именно тебе!</b> 😊\n\n"
            "По каждому тарифу ты получишь <b>50 запросов в сутки</b> для общения со мной! 💬\n\n"
            "⦁ <b>1 месяц — 250⭐️ (~429₽)</b>\n"
            "  Этот тариф — отличный способ начать. Ты получаешь всё необходимое для продуктивного старта. Это самый популярный вариант — Хит!\n\n"
            "⦁ <b>3 месяца — 600⭐️ (~1008₽)</b>\n"
            "  Выгодный тариф, который позволит тебе экономить и получать ещё больше пользы. Всего 336₽ в месяц при полном доступе к моим возможностям.\n\n"
            "⦁ <b>12 месяцев — 2000⭐️ (~3298₽)</b>\n"
            "  Для тех, кто действительно хочет погрузиться в процесс и получить максимальный эффект. Ты получаешь полный доступ по лучшей цене — всего 274₽ в месяц.\n\n"
            "<i>Выбери свой план, и я буду рядом, помогая идти к мечтам шаг за шагом!</i> ✨"
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎀1 Месяц🎀", callback_data="plan_1month")],
            [InlineKeyboardButton(text="🎀3 месяца🎀", callback_data="plan_3months")],
            [InlineKeyboardButton(text="🎀12 месяцев🎀", callback_data="plan_12months")],
        ])
        sent_message = None
        if PAY_IMAGE_PATH.startswith("http"):
            try:
                sent_message = await callback.message.bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=PAY_IMAGE_PATH,
                    caption=plans_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                logger.info(f"Отправлено сообщение с тарифами (назад), message_id: {sent_message.message_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки фото для тарифов (назад): {e}")
        else:
            if os.path.exists(PAY_IMAGE_PATH):
                try:
                    photo = FSInputFile(PAY_IMAGE_PATH)
                    sent_message = await callback.message.bot.send_photo(
                        chat_id=callback.message.chat.id,
                        photo=photo,
                        caption=plans_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                    logger.info(f"Отправлено сообщение с тарифами (назад), message_id: {sent_message.message_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки фото для тарифов (назад): {e}")
        if sent_message is None:
            sent_message = await callback.message.answer(plans_text, reply_markup=reply_markup, parse_mode="HTML")
            logger.info(f"Отправлено текстовое сообщение с тарифами (назад), message_id: {sent_message.message_id}")
        user_data[user_id]["last_pay_message_id"] = sent_message.message_id
    await save_user_data(user_id, user_data[user_id])
    await callback.answer()

async def cancel_feedback_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Нажата кнопка 'Назад' для /feedback от пользователя {user_id}")
    user_data[user_id] = user_data.get(user_id, {
        "history": [],
        "active_topic": None,
        "premium": False,
        "expiry": None,
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    })
    if user_data[user_id].get("awaiting_feedback", False):
        user_data[user_id]["awaiting_feedback"] = False
        try:
            if user_data[user_id].get("feedback_message_id"):
                await callback.message.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=user_data[user_id]["feedback_message_id"],
                )
                logger.info(f"Удалено сообщение /feedback для пользователя {user_id}")
            if user_data[user_id].get("user_feedback_message_id"):
                await callback.message.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=user_data[user_id]["user_feedback_message_id"],
                )
                logger.info(f"Удалено сообщение пользователя /feedback для {user_id}")
            await callback.message.answer(
                "Режим обратной связи отменён! 😊 Можешь продолжить общение с Эммой.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщений /feedback: {e}")
            await callback.message.answer(
                "Не удалось удалить сообщения, но режим обратной связи отменён! 😊 Можешь продолжить общение.",
                parse_mode="HTML",
            )
        user_data[user_id]["feedback_message_id"] = None
        user_data[user_id]["user_feedback_message_id"] = None
    else:
        await callback.message.answer(
            "Режим обратной связи уже завершён! 😊 Можешь продолжить общение с Эммой.",
            parse_mode="HTML",
        )
    await save_user_data(user_id, user_data[user_id])
    await callback.answer()

async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    user_id = pre_checkout_query.from_user.id
    logger.info(f"Pre-checkout query от пользователя {user_id}: {pre_checkout_query.invoice_payload}")
    await pre_checkout_query.bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    await save_user_data(user_id, user_data[user_id])

async def process_successful_payment(message: types.Message):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    logger.info(f"Успешный платёж от пользователя {user_id}: {payload}")
    if payload == "emma_premium_1month":
        duration = "1 месяц"
        expiry_date = datetime.now() + timedelta(days=30)
        amount = 250
    elif payload == "emma_premium_3months":
        duration = "3 месяца"
        expiry_date = datetime.now() + timedelta(days=90)
        amount = 600
    elif payload == "emma_premium_12months":
        duration = "12 месяцев"
        expiry_date = datetime.now() + timedelta(days=365)
        amount = 2000
    else:
        logger.error(f"Неизвестный payload: {payload}")
        await message.answer("Ой, что-то пошло не так с оплатой! 😔 Свяжитесь с поддержкой.", parse_mode="HTML")
        return
    user_data[user_id]["premium"] = True
    user_data[user_id]["expiry"] = expiry_date.timestamp()
    await save_user_data(user_id, user_data[user_id])
    await message.answer(
        f"Спасибо за поддержку, ты теперь премиум-пользователь на {duration}! 🎉 "
        f"Подписка активна до {expiry_date.strftime('%Y-%m-%d')}. "
        f"Наслаждайся всеми функциями без ограничений! 😊✨",
        parse_mode="HTML",
    )

async def handle_message(message: types.Message):
    logger.info(f"Начало обработки update для user {message.from_user.id}: {message.text[:50]}...")
    if not message.text:
        logger.info(f"Получено нетекстовое сообщение от {message.from_user.id}")
        await message.answer("Извини, я пока обрабатываю только текстовые сообщения! 😊 Напиши текст, и я помогу.")
        return
    user_id = message.from_user.id
    user_text = message.text.strip()
    logger.info(f"Получено сообщение от {user_id}: {user_text}")
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    await asyncio.sleep(0.5)
    user_data[user_id] = user_data.get(user_id, {
        "history": [],
        "active_topic": None,
        "premium": False,
        "expiry": None,
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    })
    if user_data[user_id].get("awaiting_feedback", False):
        if not FEEDBACK_CHAT_ID:
            logger.error("FEEDBACK_CHAT_ID не указан в .env")
            await message.answer("Ой, что-то пошло не так! 😔 Обратная связь временно недоступна.", parse_mode="HTML")
            user_data[user_id]["awaiting_feedback"] = False
            user_data[user_id]["feedback_message_id"] = None
            user_data[user_id]["user_feedback_message_id"] = None
            await save_user_data(user_id, user_data[user_id])
            return
        username = message.from_user.username or "Аноним"
        feedback_text = (
            f"<b>Обратная связь от @{username} (ID: {user_id})</b>\n"
            f"Сообщение: {user_text}\n\n"
            f"Чтобы ответить, используйте: <b>/reply {user_id} Ваш ответ</b>"
        )
        try:
            await message.bot.send_message(
                chat_id=FEEDBACK_CHAT_ID,
                text=feedback_text,
                parse_mode="HTML",
            )
            logger.info(f"Сообщение обратной связи от {user_id} переслано в чат {FEEDBACK_CHAT_ID}")
            try:
                if user_data[user_id].get("feedback_message_id"):
                    await message.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=user_data[user_id]["feedback_message_id"],
                    )
                    logger.info(f"Удалено сообщение /feedback для пользователя {user_id}")
                if user_data[user_id].get("user_feedback_message_id"):
                    await message.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=user_data[user_id]["user_feedback_message_id"],
                    )
                    logger.info(f"Удалено сообщение пользователя /feedback для {user_id}")
            except Exception as e:
                logger.error(f"Ошибка при удалении сообщений /feedback: {e}")
            await message.answer(
                "<b>Спасибо большое за твоё сообщение!</b> 🙌\n\n"
                "Я внимательно прочитаю твою обратную связь и передам её команде разработчиков. "
                "Каждый твой отзыв помогает делать «Эмму» умнее, добрее и полезнее для всех пользователей.\n\n"
                "Если появятся дополнительные вопросы или пожелания, не стесняйся писать — "
                "я всегда рядом, чтобы слушать и помогать.\n\n"
                "<b>Спасибо, что ты со мной!</b> 💫",
                parse_mode="HTML",
            )
            user_data[user_id]["awaiting_feedback"] = False
            user_data[user_id]["feedback_message_id"] = None
            user_data[user_id]["user_feedback_message_id"] = None
            await save_user_data(user_id, user_data[user_id])
            return
        except Exception as e:
            logger.error(f"Ошибка при пересылке сообщения в {FEEDBACK_CHAT_ID}: {e}")
            await message.answer(
                "Ой, что-то пошло не так при отправке! 😔 Попробуй ещё раз.",
                parse_mode="HTML",
            )
            user_data[user_id]["awaiting_feedback"] = False
            user_data[user_id]["feedback_message_id"] = None
            user_data[user_id]["user_feedback_message_id"] = None
            await save_user_data(user_id, user_data[user_id])
            return
    history = user_data[user_id]["history"]
    active_topic = user_data[user_id]["active_topic"]
    clarification_keywords = [
        "подробнее", "расскажи подробнее", "детали", "ещё", "tell me more", "details",
        "а что насчёт", "расскажи ещё", "больше", "углубись", "да, хочу"
    ]
    is_code_request = any(keyword in user_text.lower() for keyword in [
        "напиши код", "программа", "код на", "python", "javascript",
        "напиши программу", "код на питоне", "код калькулятора"
    ])
    history.append({"role": "user", "content": user_text})
    search_data = None
    if not is_code_request:
        is_clarification = any(keyword in user_text.lower() for keyword in clarification_keywords)
        if is_clarification:
            search_query = active_topic if active_topic else user_text
            search_data = await get_google_cse_info(search_query, active_topic)
            if search_data and not is_relevant(search_data, user_text, active_topic):
                logger.info(f"Поиск нерелевантен для '{user_text}', fallback на контекст.")
                search_data = None
        else:
            search_data = await get_google_cse_info(user_text)
            if search_data and not is_relevant(search_data, user_text):
                logger.info(f"Поиск нерелевантен для '{user_text}', fallback на контекст.")
                search_data = None
        if search_data:
            logger.info(f"Агрегировано {len(search_data)} источников")
        if isinstance(search_data, str):
            response = search_data
            await send_long_message(message, response, parse_mode="HTML")
        else:
            response = await get_unlim_response(user_id, user_text, history, is_code_request, search_data, use_html=True)
            await send_long_message(message, response, parse_mode="HTML")
    else:
        response = await get_unlim_response(user_id, user_text, history, is_code_request)
        await send_long_message(message, response, parse_mode="HTML")
    history.append({"role": "assistant", "content": response})
    user_data[user_id]["history"] = history[-20:]
    user_data[user_id]["active_topic"] = extract_topic(response)
    logger.info(f"Обновлённая история для пользователя {user_id}: {user_data[user_id]['history']}")
    logger.info(f"Активная тема для пользователя {user_id}: {user_data[user_id]['active_topic']}")
    await save_user_data(user_id, user_data[user_id])

async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data
    logger.info(f"Пользователь {user_id}: Нажата кнопка: {action}")
    await callback.message.bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    await asyncio.sleep(0.5)
    user_data[user_id] = user_data.get(user_id, {
        "history": [],
        "active_topic": None,
        "premium": False,
        "expiry": None,
        "last_pay_message_id": None,
        "awaiting_feedback": False,
        "feedback_message_id": None,
        "user_feedback_message_id": None,
    })
    if action in ["show_plans", "plan_1month", "plan_3months", "plan_12months", "back_to_plans"]:
        await handle_subscription_callback(callback)
        return
    elif action == "cancel_feedback":
        await cancel_feedback_callback(callback)
        return
    history = user_data[user_id]["history"]
    active_topic = user_data[user_id]["active_topic"]
    response = await get_unlim_response(user_id, action, history, is_code_request=False, use_html=True)
    await send_long_message(callback.message, response, parse_mode="HTML")
    history.append({"role": "assistant", "content": response})
    user_data[user_id]["history"] = history[-20:]
    user_data[user_id]["active_topic"] = extract_topic(response)
    await save_user_data(user_id, user_data[user_id])
    await callback.answer()

def register_handlers(dp: Dispatcher):
    dp.message.register(start_command, CommandStart())
    dp.message.register(info_command, Command("info"))
    dp.message.register(pay_command, Command("pay"))
    dp.message.register(clear_command, Command("clear"))
    dp.message.register(feedback_command, Command("feedback"))
    dp.message.register(cancel_command, Command("cancel"))
    dp.message.register(reply_command, Command("reply"))
    dp.message.register(handle_message)
    dp.callback_query.register(handle_callback)
    dp.pre_checkout_query.register(process_pre_checkout_query)
    dp.message.register(process_successful_payment, lambda message: message.successful_payment is not None)

user_data = {}