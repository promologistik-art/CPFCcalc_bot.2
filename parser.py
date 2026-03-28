# parser.py
import re
from typing import List, Tuple, Optional
from config import UNIT_TO_GRAMS, COMPOUND_SPLITTERS


def extract_weight(text: str) -> Tuple[Optional[float], str]:
    """
    Извлекает вес из строки. Ищет вес в любом месте.
    Возвращает (вес_в_граммах, остаток_строки_без_веса)
    """
    text = text.strip()
    original_text = text
    
    # Паттерны для поиска веса
    patterns = [
        # "100г", "150 г", "200гр"
        (r'(\d+(?:\.\d+)?)\s*г(?:рам)?', 'г'),
        # "1 кг", "2кг"
        (r'(\d+(?:\.\d+)?)\s*кг', 'кг'),
        # "2 ложки", "3 ст.л."
        (r'(\d+(?:\.\d+)?)\s*(чайных? ложек?|ч\.л\.?|столовых? ложек?|ст\.л\.?|ложек?|ложки?)', 'ложка'),
        # "тарелка", "чашка", "стакан"
        (r'(тарелк[ауи]|миск[ауи]|чашк[ауи]|стакан[ау]?)', 'единица'),
    ]
    
    best_weight = None
    best_remaining = text
    best_pattern_len = 0
    
    for pattern, unit_type in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            weight_str = match.group(1) if len(match.groups()) > 0 else "1"
            try:
                weight = float(weight_str)
            except ValueError:
                weight = 1
            
            if unit_type == 'кг':
                weight *= 1000
            elif unit_type == 'ложка':
                weight *= UNIT_TO_GRAMS.get('ложка', 10)
            elif unit_type == 'единица':
                unit_name = match.group(1).lower()
                if 'тарелк' in unit_name:
                    weight = UNIT_TO_GRAMS.get('тарелка', 300)
                elif 'миск' in unit_name:
                    weight = UNIT_TO_GRAMS.get('миска', 300)
                elif 'чашк' in unit_name:
                    weight = UNIT_TO_GRAMS.get('чашка', 200)
                elif 'стакан' in unit_name:
                    weight = UNIT_TO_GRAMS.get('стакан', 200)
            
            # Удаляем найденный вес из строки
            remaining = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
            remaining = re.sub(r'\s+', ' ', remaining).strip()
            
            # Выбираем наиболее подходящий результат (чем длиннее удалённый паттерн, тем лучше)
            pattern_len = len(match.group(0))
            if best_weight is None or pattern_len > best_pattern_len:
                best_weight = weight
                best_remaining = remaining
                best_pattern_len = pattern_len
    
    if best_weight is not None:
        return best_weight, best_remaining
    
    return None, text


def split_compound_dish(text: str) -> List[str]:
    """
    Разбивает составное блюдо на компоненты.
    Возвращает список ингредиентов.
    """
    text = text.lower().strip()
    if not text:
        return []
    
    # Пробуем разбить по каждому разделителю
    for splitter in COMPOUND_SPLITTERS:
        if splitter in text:
            parts = text.split(splitter, 1)
            left = parts[0].strip()
            right = parts[1].strip()
            
            if left and right:
                # Рекурсивно разбиваем правую часть
                right_parts = split_compound_dish(right)
                return [left] + right_parts
    
    return [text]


def parse_meal_input(text: str) -> List[Tuple[str, float]]:
    """
    Парсит сообщение пользователя с едой.
    Возвращает список кортежей (название_продукта, вес_в_граммах)
    """
    # Разбиваем по запятым
    items = [item.strip() for item in text.split(',') if item.strip()]
    
    result = []
    for item in items:
        weight, product_text = extract_weight(item)
        
        if weight is None:
            weight = 100.0
            product_text = item
        
        if product_text:
            result.append((product_text, weight))
    
    return result


def format_nutrition(protein: float, fat: float, carbs: float, calories: float) -> str:
    """Форматирует КБЖУ для вывода"""
    return f"🥩 Белки: {protein:.1f} г\n🍗 Жиры: {fat:.1f} г\n🍚 Углеводы: {carbs:.1f} г\n🔥 Калории: {calories:.0f} ккал"