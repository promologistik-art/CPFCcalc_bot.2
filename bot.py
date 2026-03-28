# bot.py
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import List, Tuple, Dict, Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from food_data import find_food, find_exact_food, normalize_search_query
from parser import parse_meal_input, format_nutrition, split_compound_dish
from db import init_db, add_meal, get_day_stats, get_period_stats, get_daily_calories

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
    waiting_for_choice = State()  # Ожидание выбора из вариантов
    waiting_for_manual_input = State()  # Ожидание ручного ввода (не используется, но оставлю)


# Временное хранилище для неоднозначных поисков
pending_searches: Dict[int, Dict] = {}


async def finalize_meal(user_id: int, state: FSMContext, results: List[Tuple], message: Message):
    """Завершает обработку приёма пищи и сохраняет в БД"""
    await state.clear()
    if user_id in pending_searches:
        del pending_searches[user_id]
    
    # Сохраняем в БД
    for name, protein, fat, carbs, calories, weight in results:
        if not name.startswith("❌"):
            # Восстанавливаем исходные КБЖУ на 100г для сохранения
            orig_protein = protein * 100 / weight if weight > 0 else 0
            orig_fat = fat * 100 / weight if weight > 0 else 0
            orig_carbs = carbs * 100 / weight if weight > 0 else 0
            orig_calories = calories * 100 / weight if weight > 0 else 0
            add_meal(user_id, name, orig_protein, orig_fat, orig_carbs, orig_calories, weight)
    
    # Формируем ответ
    meal_response = format_meal_response(results)
    
    # Получаем статистику за сегодня
    today_stats = get_day_stats(user_id)
    
    # Отправляем ответ
    await message.answer(meal_response, parse_mode="Markdown")
    await message.answer(format_day_stats(today_stats), parse_mode="Markdown")


async def process_food_item(
    product_text: str, 
    weight: float, 
    user_id: int,
    state: FSMContext
) -> Optional[Tuple[str, float, float, float, float, float]]:
    """
    Обрабатывает один продукт/блюдо рекурсивно.
    Возвращает (название, белки, жиры, углеводы, калории, вес)
    """
    # 1. Сначала ищем точное совпадение
    exact = find_exact_food(product_text)
    if exact:
        name, protein, fat, carbs, calories = exact
        factor = weight / 100.0
        return (name, protein * factor, fat * factor, carbs * factor, calories * factor, weight)
    
    # 2. Ищем частичное совпадение
    matches = find_food(product_text)
    
    if len(matches) == 1:
        name, protein, fat, carbs, calories = matches[0]
        factor = weight / 100.0
        return (name, protein * factor, fat * factor, carbs * factor, calories * factor, weight)
    
    # 3. Если несколько вариантов — сохраняем для уточнения
    if len(matches) > 1:
        return None  # Сигнал, что нужно уточнение
    
    # 4. Если не нашли — пробуем разбить на компоненты
    components = split_compound_dish(product_text)
    
    if len(components) > 1:
        # Распределяем вес равномерно между компонентами
        component_weight = weight / len(components)
        results = []
        
        for comp in components:
            result = await process_food_item(comp, component_weight, user_id, state)
            if result:
                results.append(result)
        
        if results:
            # Суммируем результаты
            total_name = " + ".join([r[0] for r in results])
            total_protein = sum(r[1] for r in results)
            total_fat = sum(r[2] for r in results)
            total_carbs = sum(r[3] for r in results)
            total_calories = sum(r[4] for r in results)
            return (total_name, total_protein, total_fat, total_carbs, total_calories, weight)
    
    # 5. Ничего не нашли
    return (f"❌ {product_text}", 0, 0, 0, 0, weight)


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
        if name.startswith("❌"):
            lines.append(f"• {name}")
        else:
            lines.append(f"• {name} ({weight:.0f}г) — {protein:.1f}/{fat:.1f}/{carbs:.1f}/{calories:.0f}")
            total_protein += protein
            total_fat += fat
            total_carbs += carbs
            total_calories += calories
    
    result = "✅ **ПРИЁМ ПИЩИ**\n\n"
    result += "\n".join(lines)
    
    if total_calories > 0:
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
    
    if len(daily_data) >= 2:
        max_day = max(daily_data, key=lambda x: x[1])
        min_day = min(daily_data, key=lambda x: x[1])
        lines.append(f"\n📈 Максимум: {max_day[0]} — {max_day[1]:.0f} ккал")
        lines.append(f"📉 Минимум: {min_day[0]} — {min_day[1]:.0f} ккал")
    
    return "\n".join(lines)


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # Очищаем состояние при старте
    await state.clear()
    user_id = message.from_user.id
    if user_id in pending_searches:
        del pending_searches[user_id]
    
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


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in pending_searches:
        del pending_searches[user_id]
    await message.answer("❌ Ввод отменён. Можете начать заново.")


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
    if daily_data:
        response += f"\n\n📅 **РАЗБИВКА ПО ДНЯМ:**\n{format_daily_breakdown(daily_data)}"
    
    await message.answer(response, parse_mode="Markdown")


@dp.message(Command("month"))
async def cmd_month(message: Message):
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    stats = get_period_stats(message.from_user.id, start_date, end_date)
    daily_data = get_daily_calories(message.from_user.id, start_date, end_date)
    
    response = format_period_stats(stats, 30)
    if daily_data:
        response += f"\n\n📅 **РАЗБИВКА ПО ДНЯМ (макс/мин):**\n{format_daily_breakdown(daily_data)}"
    
    await message.answer(response, parse_mode="Markdown")


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
    
    # Пользователь нажал "0" — пробуем найти с расширенным поиском
    if text.lower() in ['нет', 'пропустить', 'skip', '0']:
        product_name, weight, _ = pending[0]
        
        # Пробуем найти с расширенным поиском (убираем окончания)
        normalized = normalize_search_query(product_name)
        extended_matches = find_food(normalized)
        
        # Если расширенный поиск дал результаты — показываем новые варианты
        if extended_matches and len(extended_matches) > 0:
            # Сохраняем новые варианты в pending
            pending[0] = (product_name, weight, extended_matches)
            
            msg = f"🔍 Попробуем поискать по-другому для \"{product_name}\":\n\n"
            for i, (name, _, _, _, _) in enumerate(extended_matches[:10], 1):
                msg += f"{i}. {name}\n"
            msg += "\n0. Всё равно не то — попробовать разбить на составляющие\n"
            msg += "Введите номер выбранного варианта:"
            await message.answer(msg)
            return
        
        # Если расширенный поиск не дал результатов — пробуем разбить на компоненты
        components = split_compound_dish(product_name)
        
        if len(components) > 1:
            # Распределяем вес между компонентами
            component_weight = weight / len(components)
            results_from_components = []
            all_found = True
            
            for comp in components:
                matches_comp = find_food(comp)
                if matches_comp:
                    # Берём первый подходящий вариант
                    name, protein, fat, carbs, calories = matches_comp[0]
                    factor = component_weight / 100.0
                    results_from_components.append((
                        name, protein * factor, fat * factor, carbs * factor, calories * factor, component_weight
                    ))
                else:
                    all_found = False
                    results_from_components.append((f"❌ {comp}", 0, 0, 0, 0, component_weight))
            
            if all_found:
                # Успешно разбили на компоненты
                pending.pop(0)
                results.extend(results_from_components)
                
                # Переходим к следующему продукту или завершаем
                if pending:
                    next_product, next_weight, next_matches = pending[0]
                    msg = f"🔍 Найдено несколько вариантов для \"{next_product}\":\n\n"
                    for i, (name, _, _, _, _) in enumerate(next_matches[:10], 1):
                        msg += f"{i}. {name}\n"
                    msg += "\n0. Всё равно не то — попробовать разбить на составляющие\n"
                    msg += "Введите номер выбранного варианта:"
                    await message.answer(msg)
                else:
                    await finalize_meal(user_id, state, results, message)
                return
        
        # Ничего не помогло — помечаем как не найденный
        results.append((f"❌ {product_name}", 0, 0, 0, 0, weight))
        pending.pop(0)
        
        if pending:
            next_product, next_weight, next_matches = pending[0]
            msg = f"🔍 Найдено несколько вариантов для \"{next_product}\":\n\n"
            for i, (name, _, _, _, _) in enumerate(next_matches[:10], 1):
                msg += f"{i}. {name}\n"
            msg += "\n0. Всё равно не то — попробовать разбить на составляющие\n"
            msg += "Введите номер выбранного варианта:"
            await message.answer(msg)
        else:
            await finalize_meal(user_id, state, results, message)
        return
    
    # Обработка выбора номера
    try:
        choice = int(text) - 1
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите номер варианта.\n"
            "Или введите '0', чтобы попробовать найти по-другому."
        )
        return
    
    product_name, weight, matches = pending[0]
    
    if choice < 0 or choice >= len(matches):
        await message.answer(
            f"❌ Неверный номер. Введите число от 1 до {len(matches)}.\n"
            "Или введите '0', чтобы попробовать найти по-другому."
        )
        return
    
    selected = matches[choice]
    factor = weight / 100.0
    results.append((selected[0], selected[1] * factor, selected[2] * factor,
                    selected[3] * factor, selected[4] * factor, weight))
    pending.pop(0)
    
    if pending:
        # Ещё есть неоднозначные продукты
        next_product, next_weight, next_matches = pending[0]
        msg = f"🔍 Найдено несколько вариантов для \"{next_product}\":\n\n"
        for i, (name, _, _, _, _) in enumerate(next_matches[:10], 1):
            msg += f"{i}. {name}\n"
        msg += "\n0. Всё равно не то — попробовать разбить на составляющие\n"
        msg += "Введите номер выбранного варианта:"
        await message.answer(msg)
    else:
        # Все продукты обработаны
        await finalize_meal(user_id, state, results, message)


@dp.message()
async def handle_meal(message: Message, state: FSMContext):
    """Обрабатывает сообщения с едой"""
    user_id = message.from_user.id
    text = message.text
    
    # Проверяем текущее состояние
    current_state = await state.get_state()
    if current_state == ClarificationState.waiting_for_choice:
        await message.answer(
            "⏳ Сначала ответьте на предыдущий вопрос о продукте.\n"
            "Введите номер варианта или '0' чтобы попробовать найти по-другому.\n"
            "Или введите /cancel для отмены."
        )
        return
    
    # Очищаем старые данные
    if user_id in pending_searches:
        del pending_searches[user_id]
    
    # Парсим сообщение
    parsed_items = parse_meal_input(text)
    
    if not parsed_items:
        await message.answer("❌ Не удалось распознать продукты. Попробуйте ещё раз.")
        return
    
    # Обрабатываем каждый продукт
    results = []
    pending_items = []
    
    for product_text, weight in parsed_items:
        result = await process_food_item(product_text, weight, user_id, state)
        
        if result is None:
            # Нужно уточнение (несколько вариантов)
            matches = find_food(product_text)
            pending_items.append((product_text, weight, matches))
        else:
            results.append(result)
    
    if pending_items:
        # Сохраняем для уточнения
        pending_searches[user_id] = {
            'pending': pending_items,
            'results': results
        }
        await state.set_state(ClarificationState.waiting_for_choice)
        
        # Формируем сообщение с вариантами для первого неоднозначного продукта
        first_product, first_weight, first_matches = pending_items[0]
        msg = f"🔍 Найдено несколько вариантов для \"{first_product}\":\n\n"
        for i, (name, _, _, _, _) in enumerate(first_matches[:10], 1):
            msg += f"{i}. {name}\n"
        msg += "\n0. Всё равно не то — попробовать разбить на составляющие\n"
        msg += "Введите номер выбранного варианта:"
        await message.answer(msg)
        return
    
    # Все продукты обработаны, сохраняем в БД
    for name, protein, fat, carbs, calories, weight in results:
        if not name.startswith("❌"):
            orig_protein = protein * 100 / weight if weight > 0 else 0
            orig_fat = fat * 100 / weight if weight > 0 else 0
            orig_carbs = carbs * 100 / weight if weight > 0 else 0
            orig_calories = calories * 100 / weight if weight > 0 else 0
            add_meal(user_id, name, orig_protein, orig_fat, orig_carbs, orig_calories, weight)
    
    # Формируем ответ
    meal_response = format_meal_response(results)
    today_stats = get_day_stats(user_id)
    
    await message.answer(meal_response, parse_mode="Markdown")
    await message.answer(format_day_stats(today_stats), parse_mode="Markdown")


async def main():
    """Запуск бота"""
    logging.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())