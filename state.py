from aiogram.fsm.state import State, StatesGroup

user_data = {}

class UserState(StatesGroup):
    waiting_for_message = State()
    waiting_for_feedback = State()