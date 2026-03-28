# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in .env file")

# Константы для перевода бытовых единиц в граммы
UNIT_TO_GRAMS = {
    "ложка": 10,      # столовая ложка
    "чайная ложка": 5,
    "ч.л.": 5,
    "ст.л.": 10,
    "тарелка": 300,
    "миска": 300,
    "чашка": 200,
    "стакан": 200,
    "г": 1,
    "грамм": 1,
    "кг": 1000,
}

# Союзы для разделения составных блюд
COMPOUND_CONJUNCTIONS = ["с", "со", "и", "в", "во", "на", "сок", "соус", "подлив"]