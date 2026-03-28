# db.py
import sqlite3
from datetime import datetime, date
from typing import List, Tuple, Dict, Optional

DB_NAME = 'user_stats.db'


def init_db():
    """Инициализирует базу данных"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            protein REAL NOT NULL,
            fat REAL NOT NULL,
            carbs REAL NOT NULL,
            calories REAL NOT NULL,
            weight_grams REAL NOT NULL,
            timestamp DATETIME NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def add_meal(user_id: int, product_name: str, protein: float, fat: float,
             carbs: float, calories: float, weight_grams: float, timestamp: datetime = None):
    """Добавляет запись о приёме пищи"""
    if timestamp is None:
        timestamp = datetime.now()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Пересчитываем КБЖУ на указанный вес
    factor = weight_grams / 100.0
    actual_protein = protein * factor
    actual_fat = fat * factor
    actual_carbs = carbs * factor
    actual_calories = calories * factor
    
    cursor.execute('''
        INSERT INTO meals (user_id, product_name, protein, fat, carbs, calories, weight_grams, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, product_name, actual_protein, actual_fat,
          actual_carbs, actual_calories, weight_grams, timestamp))
    
    conn.commit()
    conn.close()


def get_day_stats(user_id: int, target_date: date = None) -> Dict[str, float]:
    """Возвращает суммарные КБЖУ за день"""
    if target_date is None:
        target_date = date.today()
    
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT SUM(protein), SUM(fat), SUM(carbs), SUM(calories)
        FROM meals
        WHERE user_id = ? AND timestamp BETWEEN ? AND ?
    ''', (user_id, start, end))
    
    result = cursor.fetchone()
    conn.close()
    
    return {
        'protein': result[0] or 0.0,
        'fat': result[1] or 0.0,
        'carbs': result[2] or 0.0,
        'calories': result[3] or 0.0
    }


def get_period_stats(user_id: int, start_date: date, end_date: date) -> Dict[str, float]:
    """Возвращает суммарные КБЖУ за период"""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT SUM(protein), SUM(fat), SUM(carbs), SUM(calories)
        FROM meals
        WHERE user_id = ? AND timestamp BETWEEN ? AND ?
    ''', (user_id, start, end))
    
    result = cursor.fetchone()
    conn.close()
    
    return {
        'protein': result[0] or 0.0,
        'fat': result[1] or 0.0,
        'carbs': result[2] or 0.0,
        'calories': result[3] or 0.0
    }


def get_daily_calories(user_id: int, start_date: date, end_date: date) -> List[Tuple[str, float]]:
    """Возвращает дневную калорийность за период"""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DATE(timestamp), SUM(calories)
        FROM meals
        WHERE user_id = ? AND timestamp BETWEEN ? AND ?
        GROUP BY DATE(timestamp)
        ORDER BY DATE(timestamp)
    ''', (user_id, start, end))
    
    results = cursor.fetchall()
    conn.close()
    
    return [(row[0], row[1]) for row in results]