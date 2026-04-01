# NU LibCal Booking Bot 🚀

Автоматизация бронирования комнат в библиотеке NU через Playwright.

## Особенности
- **Relative Click System**: Не промахивается мимо ячеек при прыжках страницы.
- **Image Recognition**: Проверяет доступность слотов по цвету пикселей (зеленый/красный).
- **Date Navigation**: Умеет пролистывать календарь на нужный месяц.

## Как запустить
1. `pip install -r requirements.txt`
2. `playwright install chromium`
3. Настроить `config.py` или `.env`
4. `python main.py`
5. `python -m venv venv`
6. `venv\Scripts\activate`
7. Создайте файл с именем '.env' и  скопируйте и вставьте туда код из файла '.env.example' и заполните свои данные
