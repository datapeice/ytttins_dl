#!/bin/bash
# Скрипт активации виртуального окружения

echo "🐍 Активация виртуального окружения..."

if [ ! -d "venv" ]; then
    echo "❌ Виртуальное окружение не найдено!"
    echo "Создаю venv..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 Установка зависимостей..."
    pip install -q --upgrade pip
    pip install -r requirements.txt
    echo "✅ Окружение готово!"
else
    source venv/bin/activate
    echo "✅ Окружение активировано"
fi

echo ""
echo "Для деактивации используйте: deactivate"
echo "Для запуска бота: python main.py"
echo "Для теста Cobalt: python test_cobalt.py <youtube_url>"
echo ""
