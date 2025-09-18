import spacy
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

# Загружаем модель spaCy для русского языка
nlp = spacy.load("ru_core_news_md")

# Загружаем базу знаний
try:
    with open('knowledge_base.json', 'r', encoding='utf-8') as f:
        kb = json.load(f)
except FileNotFoundError:
    print("Ошибка: Файл knowledge_base.json не найден.")
    raise
except json.JSONDecodeError:
    print("Ошибка: Неверный формат JSON в knowledge_base.json.")
    raise

# Собираем данные для обучения
intents = []
utterances = []
for intent_data in kb['intents']:
    for pattern in intent_data['patterns']:
        intents.append(intent_data['intent'])
        utterances.append(pattern)

# Проверяем, есть ли данные для обучения
if not utterances:
    print("Ошибка: В базе знаний нет паттернов для обучения.")
    raise ValueError("Пустая база знаний")

# Обучаем TF-IDF векторайзер и модель
vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(utterances)
model = LogisticRegression(multi_class='multinomial', max_iter=1000)
model.fit(X, intents)

def predict_intent(text):
    # Строгая проверка ключевых слов для write_code
    code_keywords = [
        "напиши код", "код на python", "программа на", "как написать код",
        "код для", "python скрипт", "javascript код", "код на javascript",
        "напиши программу", "код на питоне", "код калькулятора"
    ]
    if any(keyword in text.lower() for keyword in code_keywords):
        print(f"Строгая проверка: Текст '{text}' классифицирован как write_code")
        return "write_code"
    
    # Лемматизация текста
    doc = nlp(text.lower())
    lemmatized = " ".join([token.lemma_ for token in doc])
    
    # Векторизация и предсказание
    X_test = vectorizer.transform([lemmatized])
    intent = model.predict(X_test)[0]
    confidence = np.max(model.predict_proba(X_test))
    
    print(f"LogisticRegression для '{text}': {intent}, уверенность: {confidence:.2f}")
    return intent