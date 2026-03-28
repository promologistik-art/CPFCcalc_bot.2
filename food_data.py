# food_data.py
import json
import re
from typing import List, Tuple, Optional, Dict

# Загружаем данные из JSON
with open('data.json', 'r', encoding='utf-8') as f:
    RAW_FOOD_DATA = json.load(f)

# Список всех продуктов для поиска
FOOD_LIST: List[Tuple[str, float, float, float, float]] = []
for name, data in RAW_FOOD_DATA.items():
    FOOD_LIST.append((
        name,
        data['protein'],
        data['fat'],
        data['carbohydrates'],
        data['calories']
    ))

# Индекс для быстрого поиска (словарь: нормализованное название -> список продуктов)
NORMALIZED_INDEX: Dict[str, List[Tuple[str, float, float, float, float]]] = {}


def _normalize_name(name: str) -> str:
    """Нормализует название для поиска: нижний регистр, убираем окончания, знаки препинания"""
    normalized = name.lower()
    # Убираем знаки препинания
    normalized = re.sub(r'[^\w\s]', '', normalized)
    # Убираем окончания (упрощённо)
    normalized = re.sub(r'(ы|и|а|я|о|е|у|ю|ё|ь|ъ|й)$', '', normalized)
    return normalized.strip()


def _build_index():
    """Строит индекс для быстрого поиска"""
    global NORMALIZED_INDEX
    for product in FOOD_LIST:
        name = product[0]
        normalized = _normalize_name(name)
        if normalized not in NORMALIZED_INDEX:
            NORMALIZED_INDEX[normalized] = []
        NORMALIZED_INDEX[normalized].append(product)


# Строим индекс при загрузке
_build_index()


def find_food(query: str) -> List[Tuple[str, float, float, float, float]]:
    """
    Ищет продукты по запросу (частичное совпадение, регистронезависимо)
    Возвращает список кортежей (название, белки, жиры, углеводы, калории)
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return []
    
    # Сначала ищем точное совпадение нормализованных названий
    normalized_query = _normalize_name(query_lower)
    if normalized_query in NORMALIZED_INDEX:
        return NORMALIZED_INDEX[normalized_query][:10]  # не больше 10 вариантов
    
    # Затем частичное совпадение
    results = []
    for name, protein, fat, carbs, calories in FOOD_LIST:
        if query_lower in name.lower():
            results.append((name, protein, fat, carbs, calories))
            if len(results) >= 20:  # ограничиваем количество результатов
                break
    
    return results


def find_exact_food(query: str) -> Optional[Tuple[str, float, float, float, float]]:
    """Ищет точное совпадение по названию (регистронезависимо)"""
    query_lower = query.lower().strip()
    for product in FOOD_LIST:
        if product[0].lower() == query_lower:
            return product
    return None