# food_data.py
import json
import re
from typing import List, Tuple, Optional, Dict
from config import WORD_ENDINGS

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

# Индекс для быстрого поиска по нормализованным названиям
NORMALIZED_INDEX: Dict[str, List[Tuple[str, float, float, float, float]]] = {}


def normalize_name(name: str) -> str:
    """Нормализует название продукта для индексации"""
    normalized = name.lower()
    # Убираем знаки препинания
    normalized = re.sub(r'[^\w\s]', '', normalized)
    # Убираем лишние пробелы
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def normalize_search_query(query: str) -> str:
    """Нормализует поисковый запрос (убирает окончания)"""
    query = query.lower().strip()
    for ending in WORD_ENDINGS:
        query = re.sub(ending, '', query)
    return query.strip()


def _build_index():
    """Строит индекс для быстрого поиска"""
    global NORMALIZED_INDEX
    for product in FOOD_LIST:
        name = product[0]
        normalized = normalize_name(name)
        if normalized not in NORMALIZED_INDEX:
            NORMALIZED_INDEX[normalized] = []
        NORMALIZED_INDEX[normalized].append(product)


# Строим индекс при загрузке
_build_index()


def find_food(query: str) -> List[Tuple[str, float, float, float, float]]:
    """
    Ищет продукты по запросу с улучшенной логикой.
    Возвращает список кортежей (название, белки, жиры, углеводы, калории)
    """
    query = query.lower().strip()
    if not query:
        return []
    
    results = []
    seen = set()
    
    # Нормализуем запрос
    normalized_query = normalize_name(query)
    search_normalized = normalize_search_query(query)
    
    # Разбиваем запрос на слова для поиска по частям
    query_words = query.split()
    
    for name, protein, fat, carbs, calories in FOOD_LIST:
        name_lower = name.lower()
        
        # Проверяем различные критерии совпадения
        score = 0
        reasons = []
        
        # 1. Точное совпадение нормализованных названий
        if normalize_name(name_lower) == normalized_query:
            score += 100
            reasons.append("exact_normalized")
        
        # 2. Прямое вхождение запроса в название
        if query in name_lower:
            score += 50
            reasons.append("direct_match")
        
        # 3. Нормализованный запрос в названии
        if search_normalized and search_normalized in name_lower:
            score += 30
            reasons.append("normalized_match")
        
        # 4. Название начинается с запроса
        if name_lower.startswith(query):
            score += 40
            reasons.append("starts_with")
        
        # 5. Любое слово из запроса есть в названии
        for word in query_words:
            if len(word) > 2 and word in name_lower:
                score += 10
                reasons.append(f"word_match:{word}")
        
        if score > 0 and name not in seen:
            results.append((name, protein, fat, carbs, calories, score))
            seen.add(name)
    
    # Сортируем по релевантности (по убыванию score)
    results.sort(key=lambda x: x[5], reverse=True)
    
    # Возвращаем только названия и КБЖУ (без score)
    return [(r[0], r[1], r[2], r[3], r[4]) for r in results[:15]]


def find_exact_food(query: str) -> Optional[Tuple[str, float, float, float, float]]:
    """Ищет точное совпадение по названию"""
    query_lower = query.lower().strip()
    for product in FOOD_LIST:
        if product[0].lower() == query_lower:
            return product
    return None


def get_all_food_names() -> List[str]:
    """Возвращает список всех названий продуктов (для отладки)"""
    return [name for name, _, _, _, _ in FOOD_LIST]