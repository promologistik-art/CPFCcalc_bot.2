# parser.py
import re
from typing import List, Tuple, Optional
from config import UNIT_TO_GRAMS, COMPOUND_CONJUNCTIONS


def extract_weight(text: str) -> Tuple[Optional[float], str]:
    """
    Извлекает вес из строки. Ищет вес в любом месте.
    Возвращает (вес_в_граммах, остаток_строки_без_веса)
    """
    text = text.strip()
    
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
    
    best_match = None
    best_weight = None
    best_remaining = text
    
    for pattern, unit_type in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
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
            
            # Выбираем первое найденное или с наибольшим весом
            if best_match is None:
                best_match = pattern
                best_weight = weight
                best_remaining = remaining
    
    if best_weight is not None:
        return best_weight, best_remaining
    
    return None, text


def split_compound_dish(text: str) -> List[str]:
    """
    Разбивает составное блюдо на компоненты.
    """
    text = text.lower().strip()
    
    # Ищем союзы
    for conj in COMPOUND_CONJUNCTIONS:
        pattern = rf'\b{conj}\b'
        if re.search(pattern, text):
            parts = re.split(pattern, text, maxsplit=1)
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()
                if left and right:
                    return [left, right]
    
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