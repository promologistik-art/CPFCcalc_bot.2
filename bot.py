# bot.py
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import List, Tuple, Dict, Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from food_data import find_food, find_exact_food
from parser import parse_meal_input, format_nutrition
from db import init_db, add_meal, get_day_stats, get_period_stats, get_daily_calories

# Глобальный словарь для хранения ожидающих уточнений
pending_searches: Dict[int, Dict] = {}


# Добавляем хендлер для /start и /cancel в состоянии уточнения
@dp.message(ClarificationState.waiting_for_choice, Command("start"))
async def cmd_start_in_clarification(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in pending_searches:
        del pending_searches[message.from_user.id]
    await cmd_start(message)


@dp.message(ClarificationState.waiting_for_choice, Command("cancel"))
async def cmd_cancel_in_clarification(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in pending_searches:
        del pending_searches[message.from_user.id]
    await message.answer("❌ Ввод отменён. Можете начать заново.")


@dp.message(ClarificationState.waiting_for_choice)
async def handle_clarification(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id not in pending_searches:
        await state.clear()
        await message.answer("⏳ Сеанс уточнения истёк. Напишите продукты заново.")
        return
    
    search_data = pending_searches[user_id]
    pending = search_data['pending']
    results = search_data['results']
    
    # Проверяем, хочет ли пользователь пропустить
    if text.lower() in ['нет', 'пропустить', 'skip', '0']:
        product_name, weight, _ = pending[0]
        results.append((f"❌ {product_name}", 0, 0, 0, 0, weight))
        pending.pop(0)
    else:
        try:
            choice = int(text) - 1
        except ValueError:
            await message.answer("❌ Пожалуйста, введите номер варианта или '0' чтобы пропустить.")
            return
        
        if choice < 0 or choice >= len(pending[0][2]):
            await message.answer("❌ Неверный номер. Попробуйте снова.")
            return
        
        product_name, weight, matches = pending[0]
        selected = matches[choice]
        
        factor = weight / 100.0
        results.append((selected[0], selected[1] * factor, selected[2] * factor,
                        selected[3] * factor, selected[4] * factor, weight))
        pending.pop(0)
    
    if pending:
        next_product, next_weight, next_matches = pending[0]
        msg = f"🔍 Найдено несколько вариантов для \"{next_product}\":\n\n"
        for i, (name, _, _, _, _) in enumerate(next_matches[:10], 1):
            msg += f"{i}. {name}\n"
        msg += "\n0. Нет моего варианта (пропустить)\n"
        msg += "Введите номер выбранного варианта."
        await message.answer(msg)
    else:
        await state.clear()
        del pending_searches[user_id]
        
        # Сохраняем в БД
        for name, protein, fat, carbs, calories, weight in results:
            if not name.startswith("❌"):
                orig_protein = protein * 100 / weight if weight > 0 else 0
                orig_fat = fat * 100 / weight if weight > 0 else 0
                orig_carbs = carbs * 100 / weight if weight > 0 else 0
                orig_calories = calories * 100 / weight if weight > 0 else 0
                add_meal(user_id, name, orig_protein, orig_fat, orig_carbs, orig_calories, weight)
        
        meal_response = format_meal_response(results)
        today_stats = get_day_stats(user_id)
        
        await message.answer(meal_response, parse_mode="Markdown")
        await message.answer(format_day_stats(today_stats), parse_mode="Markdown")


# Обновляем основной хендлер сообщений — добавляем проверку состояния
@dp.message()
async def handle_meal(message: Message, state: FSMContext):
    """Обрабатывает сообщения с едой"""
    current_state = await state.get_state()
    
    # Если мы в процессе уточнения, не начинаем новый ввод
    if current_state == ClarificationState.waiting_for_choice:
        await message.answer("⏳ Сначала ответьте на предыдущий вопрос о продукте.\nИли введите /cancel для отмены.")
        return
    
    user_id = message.from_user.id
    text = message.text
    
    # Очищаем старые данные если есть
    if user_id in pending_searches:
        del pending_searches[user_id]
    
    results = await process_meal(user_id, text, state)
    
    if results is None:
        return
    
    # Сохраняем в БД
    for name, protein, fat, carbs, calories, weight in results:
        if not name.startswith("❌"):
            orig_protein = protein * 100 / weight if weight > 0 else 0
            orig_fat = fat * 100 / weight if weight > 0 else 0
            orig_carbs = carbs * 100 / weight if weight > 0 else 0
            orig_calories = calories * 100 / weight if weight > 0 else 0
            add_meal(user_id, name, orig_protein, orig_fat, orig_carbs, orig_calories, weight)
    
    meal_response = format_meal_response(results)
    today_stats = get_day_stats(user_id)
    
    await message.answer(meal_response, parse_mode="Markdown")
    await message.answer(format_day_stats(today_stats), parse_mode="Markdown")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Инициализация БД
init_db()


# Состояния для FSM
class ClarificationState(StatesGroup):
    waiting_for_choice = State()  # Ожидание выбора из нескольких вариантов


# Временное хранилище для неоднозначных поисков
pending_searches: Dict[int, Dict] = {}


def format_meal_response(products: List[Tuple[str, float, float, float, float, float]]) -> str:
    """Форматирует ответ для одного приёма пищи"""
    if not products:
        return "❌ Не удалось распознать ни одного продукта."
    
    total_protein = 0.0
    total_fat = 0.0
    total_carbs = 0.0
    total_calories = 0.0
    
    lines = []
    for name, protein, fat, carbs, calories, weight in products:
        lines.append(f"• {name} ({weight:.0f}г) — {protein:.1f}/{fat:.1f}/{carbs:.1f}/{calories:.0f}")
        total_protein += protein
        total_fat += fat
        total_carbs += carbs
        total_calories += calories
    
    result = "✅ **ПРИЁМ ПИЩИ**\n\n"
    result += "\n".join(lines)
    result += f"\n\n**ИТОГО ЗА ПРИЁМ:**\n{format_nutrition(total_protein, total_fat, total_carbs, total_calories)}"
    
    return result


def format_day_stats(stats: Dict[str, float]) -> str:
    """Форматирует дневную статистику"""
    return f"📊 **ИТОГО ЗА СЕГОДНЯ:**\n{format_nutrition(stats['protein'], stats['fat'], stats['carbs'], stats['calories'])}"


def format_period_stats(stats: Dict[str, float], days: int) -> str:
    """Форматирует статистику за период"""
    return f"📊 **ИТОГО ЗА {days} ДНЕЙ:**\n{format_nutrition(stats['protein'], stats['fat'], stats['carbs'], stats['calories'])}"


def format_daily_breakdown(daily_data: List[Tuple[str, float]]) -> str:
    """Форматирует разбивку по дням"""
    if not daily_data:
        return "Нет данных за этот период."
    
    lines = []
    for day, calories in daily_data:
        lines.append(f"{day}: {calories:.0f} ккал")
    
    # Находим максимум и минимум
    if len(daily_data) >= 2:
        max_day = max(daily_data, key=lambda x: x[1])
        min_day = min(daily_data, key=lambda x: x[1])
        lines.append(f"\n📈 Максимум: {max_day[0]} — {max_day[1]:.0f} ккал")
        lines.append(f"📉 Минимум: {min_day[0]} — {min_day[1]:.0f} ккал")
    
    return "\n".join(lines)


async def process_meal(user_id: int, text: str, state: FSMContext) -> Optional[List[Tuple[str, float, float, float, float, float]]]:
    """
    Обрабатывает сообщение с едой.
    Возвращает список кортежей (название, белки, жиры, углеводы, калории, вес)
    """
    # Парсим сообщение
    parsed_items = parse_meal_input(text)
    
    results = []
    pending = []
    
    for product_name, weight in parsed_items:
        # Ищем продукт
        matches = find_food(product_name)
        
        if len(matches) == 0:
            results.append((f"❌ {product_name}", 0, 0, 0, 0, weight))
        elif len(matches) == 1:
            name, protein, fat, carbs, calories = matches[0]
            factor = weight / 100.0
            results.append((name, protein * factor, fat * factor, carbs * factor, calories * factor, weight))
        else:
            # Несколько вариантов — сохраняем для уточнения
            pending.append((product_name, weight, matches))
    
    if pending:
        # Сохраняем состояние для уточнения
        pending_searches[user_id] = {
            'pending': pending,
            'results': results,
            'text': text
        }
        await state.set_state(ClarificationState.waiting_for_choice)
        
        # Формируем сообщение с вариантами для первого неоднозначного продукта
        first_product, first_weight, first_matches = pending[0]
        msg = f"🔍 Найдено несколько вариантов для \"{first_product}\":\n\n"
        for i, (name, _, _, _, _) in enumerate(first_matches[:10], 1):
            msg += f"{i}. {name}\n"
        msg += "\nВведите номер выбранного варианта."
        
        await bot.send_message(user_id, msg)
        return None
    
    return results


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я бот для учёта питания.\n\n"
        "📝 **Как пользоваться:**\n"
        "Просто напишите, что вы съели. Например:\n"
        "• `омлет 150г`\n"
        "• `кофе с молоком, бутерброд с сыром 100г`\n"
        "• `борщ со сметаной, хлеб 50г`\n\n"
        "📊 **Команды:**\n"
        "/stats — статистика за сегодня\n"
        "/week — статистика за неделю\n"
        "/month — статистика за месяц\n"
        "/cancel — отменить текущий ввод",
        parse_mode="Markdown"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    stats = get_day_stats(message.from_user.id)
    await message.answer(format_day_stats(stats), parse_mode="Markdown")


@dp.message(Command("week"))
async def cmd_week(message: Message):
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    stats = get_period_stats(message.from_user.id, start_date, end_date)
    daily_data = get_daily_calories(message.from_user.id, start_date, end_date)
    
    response = format_period_stats(stats, 7)
    response += f"\n\n📅 **РАЗБИВКА ПО ДНЯМ:**\n{format_daily_breakdown(daily_data)}"
    
    await message.answer(response, parse_mode="Markdown")


@dp.message(Command("month"))
async def cmd_month(message: Message):
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    stats = get_period_stats(message.from_user.id, start_date, end_date)
    daily_data = get_daily_calories(message.from_user.id, start_date, end_date)
    
    response = format_period_stats(stats, 30)
    response += f"\n\n📅 **РАЗБИВКА ПО ДНЯМ (макс/мин):**\n{format_daily_breakdown(daily_data)}"
    
    await message.answer(response, parse_mode="Markdown")


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in pending_searches:
        del pending_searches[message.from_user.id]
    await message.answer("❌ Ввод отменён. Можете начать заново.")


@dp.message(ClarificationState.waiting_for_choice)
async def handle_clarification(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id not in pending_searches:
        await state.clear()
        await message.answer("⏳ Сеанс уточнения истёк. Напишите продукты заново.")
        return
    
    try:
        choice = int(message.text.strip()) - 1
    except ValueError:
        await message.answer("❌ Пожалуйста, введите номер варианта.")
        return
    
    search_data = pending_searches[user_id]
    pending = search_data['pending']
    results = search_data['results']
    
    if choice < 0 or choice >= len(pending[0][2]):
        await message.answer("❌ Неверный номер. Попробуйте снова.")
        return
    
    # Выбранный продукт
    product_name, weight, matches = pending[0]
    selected = matches[choice]
    
    # Добавляем выбранный продукт в результаты
    factor = weight / 100.0
    results.append((selected[0], selected[1] * factor, selected[2] * factor,
                    selected[3] * factor, selected[4] * factor, weight))
    
    # Убираем обработанный продукт из списка ожидающих
    pending.pop(0)
    
    if pending:
        # Ещё есть неоднозначные продукты
        next_product, next_weight, next_matches = pending[0]
        msg = f"🔍 Найдено несколько вариантов для \"{next_product}\":\n\n"
        for i, (name, _, _, _, _) in enumerate(next_matches[:10], 1):
            msg += f"{i}. {name}\n"
        msg += "\nВведите номер выбранного варианта."
        await message.answer(msg)
    else:
        # Все продукты обработаны
        await state.clear()
        del pending_searches[user_id]
        
        # Сохраняем в БД
        for name, protein, fat, carbs, calories, weight in results:
            if not name.startswith("❌"):  # Не сохраняем ненайденные
                add_meal(user_id, name, protein * 100 / weight if weight > 0 else 0,
                        fat * 100 / weight if weight > 0 else 0,
                        carbs * 100 / weight if weight > 0 else 0,
                        calories * 100 / weight if weight > 0 else 0,
                        weight)
        
        # Формируем ответ
        meal_response = format_meal_response(results)
        
        # Получаем статистику за сегодня
        today_stats = get_day_stats(user_id)
        
        # Отправляем ответ
        await message.answer(meal_response, parse_mode="Markdown")
        await message.answer(format_day_stats(today_stats), parse_mode="Markdown")


@dp.message()
async def handle_meal(message: Message, state: FSMContext):
    """Обрабатывает сообщения с едой"""
    user_id = message.from_user.id
    text = message.text
    
    # Проверяем, не в процессе ли уточнения
    current_state = await state.get_state()
    if current_state:
        return  # Уже обрабатывается в другом хендлере
    
    results = await process_meal(user_id, text, state)
    
    if results is None:
        return  # Ожидаем уточнения
    
    # Сохраняем в БД
    for name, protein, fat, carbs, calories, weight in results:
        if not name.startswith("❌"):  # Не сохраняем ненайденные
            add_meal(user_id, name, protein * 100 / weight if weight > 0 else 0,
                    fat * 100 / weight if weight > 0 else 0,
                    carbs * 100 / weight if weight > 0 else 0,
                    calories * 100 / weight if weight > 0 else 0,
                    weight)
    
    # Формируем ответ
    meal_response = format_meal_response(results)
    
    # Получаем статистику за сегодня
    today_stats = get_day_stats(user_id)
    
    # Отправляем ответ
    await message.answer(meal_response, parse_mode="Markdown")
    await message.answer(format_day_stats(today_stats), parse_mode="Markdown")


async def main():
    """Запуск бота"""
    logging.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())