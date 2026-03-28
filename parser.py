# parser.py
import re
from typing import List, Tuple, Optional
from config import UNIT_TO_GRAMS, COMPOUND_CONJUNCTIONS


def extract_weight(text: str) -> Tuple[Optional[float], str]:
    """
    Извлекает вес из строки.
    Возвращает (вес_в_граммах, остаток_строки_без_веса)
    """
    text = text.strip()
    original_text = text
    
    # Паттерны для поиска веса (в порядке приоритета)
    patterns = [
        # "100г", "150 г", "200гр"
        (r'^(\d+(?:\.\d+)?)\s*г(?:рам)?\b', 'г'),
        # "1 кг", "2кг"
        (r'^(\d+(?:\.\d+)?)\s*кг\b', 'кг'),
        # "2 ложки", "3 ст.л." — только в начале строки
        (r'^(\d+(?:\.\d+)?)\s*(чайных? ложек?|ч\.л\.?|столовых? ложек?|ст\.л\.?|ложек?|ложки?)\b', 'ложка'),
        # "тарелка", "чашка", "стакан" — только в начале строки
        (r'^(тарелк[ауи]|миск[ауи]|чашк[ауи]|стакан[ау]?)\b', 'единица'),
        # Вес в конце строки (для случаев, когда продукт написан после веса)
        (r'(\d+(?:\.\d+)?)\s*г(?:рам)?\s*$', 'г'),
        (r'(\d+(?:\.\d+)?)\s*кг\s*$', 'кг'),
    ]
    
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
            # Если осталась пустая строка или только союзы — пробуем следующий паттерн
            if not remaining or remaining.lower() in COMPOUND_CONJUNCTIONS:
                continue
            return weight, remaining
    
    # Если вес не найден, возвращаем None и исходный текст
    return None, text


def split_compound_dish(text: str) -> List[str]:
    """
    Разбивает составное блюдо на компоненты только если это необходимо.
    Возвращает список компонентов.
    """
    text = text.lower().strip()
    
    # Ищем союзы
    for conj in COMPOUND_CONJUNCTIONS:
        # Ищем союз как отдельное слово
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
    # Разбиваем по запятым на отдельные блюда/продукты
    items = [item.strip() for item in text.split(',') if item.strip()]
    
    result = []
    for item in items:
        # Извлекаем вес
        weight, product_text = extract_weight(item)
        
        # Если вес не найден, используем значение по умолчанию 100г
        if weight is None:
            weight = 100.0
            product_text = item
        
        # Проверяем, не пустая ли строка после удаления веса
        if not product_text:
            continue
        
        result.append((product_text, weight))
    
    return result


def format_nutrition(protein: float, fat: float, carbs: float, calories: float) -> str:
    """Форматирует КБЖУ для вывода"""
    return f"🥩 Белки: {protein:.1f} г\n🍗 Жиры: {fat:.1f} г\n🍚 Углеводы: {carbs:.1f} г\n🔥 Калории: {calories:.0f} ккал"