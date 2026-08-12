# GhostMarket Backend API & Telegram Bot

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-37814A?style=for-the-badge&logo=celery&logoColor=white)
![NGINX](https://img.shields.io/badge/NGINX-009639?style=for-the-badge&logo=nginx&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)


Демо-версия бэкенд-сервера интернет-магазина [ghostmarkt](https://ghostmarkt.com). Документация по API и openapi-схема доступны соответственно по поддоменам [docs](https://docs.ghostmarkt.com) и [api](https://api.ghostmarkt.com).
Репозиторий представляет собой изолированную серверную часть проекта (API на FastAPI + Telegram-бот на aiogram + фоновые задачи на Celery).

---

## Стек технологий

* **Фреймворк:** FastAPI (Python 3.12+)
* **База данных:** PostgreSQL 15 (ORM: SQLAlchemy 2.0 (асинхронный режим) + Alembic для миграций)
* **Кэширование и очереди:** Redis
* **Фоновые задачи:** Celery
* **Веб-сервер и обратный прокси:** Nginx (маршрутизация внешних запросов, SSL, раздача статических медиафайлов)
* **Telegram-бот:** aiogram 3.x (поддержка WebApp интеграции)
* **Тестирование:** pytest

---

## Структура проекта

```text
GhostServer/
├── backend/
│   ├── src/                  # Исходный код приложения
│   │   ├── auth/             # Авторизация по почте и OTP, JWT сессии в cookies
│   │   ├── bot/              # Телеграм-бот (клавиатуры, хэндлеры, вебхуки)
│   │   ├── cdek/             # Интеграция со СДЭК (проксирование)
│   │   ├── infrastructure/   # Интеграция с ИИ для переводов (AllTokens API)
│   │   ├── notifications/    # Система отправки email и уведомлений в TG
│   │   ├── orders/           # Управление заказами, резервирование склада, Celery-задачи
│   │   ├── payments/         # Интеграция с Робокассой (прием вебхуков)
│   │   ├── products/         # Управление каталогом товаров, промокодами и медиафайлами
│   │   ├── shared/           # Общие хелперы, базовые DAO, сессии БД и Celery-клиент
│   │   ├── config.py         # Загрузка и валидация конфигурации через Pydantic Settings
│   │   └── main.py           # Инициализация FastAPI приложения и роутера
│   ├── migrations/           # Миграции базы данных Alembic
│   ├── templates/            # HTML-шаблоны для рассылок и писем
│   ├── tests/                # Unit и интеграционные тесты
│   ├── Dockerfile            # Инструкция сборки Docker-образа
│   ├── pytest.ini            # Настройки тестового окуржения
│   ├── requirements.txt      # Зависимости Python
│   └── .env.example          # Пример конфигурационного файла
├── docker-compose.dev.yml    # Конфигурация Docker Compose для локального демо-запуска
└── README.md                 # Документация проекта (вы здесь)
```

---

## Быстрый запуск (Development / Demo)

Проект оптимизирован для запуска и тестирования в Docker-окружении с использованием файла `docker-compose.dev.yml`.

### 1. Подготовка переменных окружения
Перейдите в папку `backend/` и создайте файл `.env` на основе примера:
```bash
cp backend/.env.example backend/.env
```
Замените значения переменных в созданном файле `.env` на ваши собственные (токен Telegram-бота, настройки почты и т.д.).

### 2. Запуск контейнеров
Запустите Docker Compose в фоновом режиме:
```bash
docker compose -f docker-compose.dev.yml up -d --build
```
Эта команда автоматически соберет и запустит следующие сервисы:
* `postgres` – СУБД PostgreSQL (внутренний порт `5432` контейнера, мапится на `5435` хоста).
* `redis` – Хранилище Redis для кеша, FSM бота и очередей Celery (порт `6379`).
* `mailhog` – Локальный SMTP заглушка-сервер для тестирования писем (веб-панель доступна на `http://localhost:8025`).
* `nginx` – Веб-сервер и обратный прокси (внешний порт `8000`), маршрутизирует трафик к FastAPI-приложению и раздает медиафайлы.
* `web` – FastAPI-сервер с автоматической перезагрузкой кода (внутренний порт `8000` в сети Docker, проксируется через Nginx).
* `worker` – Celery-воркер для обработки фоновых задач (отправка писем, отмена неоплаченных заказов по таймеру и т.д.).

### 3. Инициализация базы данных (применение миграций)
После первого запуска контейнеров примените миграции базы данных:
```bash
docker compose -f docker-compose.dev.yml exec web alembic upgrade head
```

---

## Документация API (FastAPI OpenAPI)

Интерактивная спецификация API доступна сразу после запуска сервера по следующим адресам:
* **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

Все маршруты бэкенда детально задокументированы, включая возможные ошибки (400, 401, 403, 404) и форматы JSON-схем запросов/ответов.

---

## Запуск тестов

Тестовый набор покрывает ключевую бизнес-логику (авторизация, создание заказов, расчет скидок по промокодам и интеграции). Запустить тесты можно в контейнере бэкенда:
```bash
docker compose -f docker-compose.dev.yml exec web pytest
```

---

## Важные замечания при развертывании

* **Режим разработки:** В файле `docker-compose.dev.yml` включен режим монтирования директорий (volumes) для горячей перезагрузки кода.
* **Безопасность кук:** В режиме разработки (`DEBUG=True` в `.env`) куки сессии авторизации создаются без флага `Secure`. Для использования HTTPS в продакшене обязательно переключите `COOKIE__SECURE=true` и `DEBUG=False`.
* **Почтовый сервер:** По умолчанию отправка писем настроена на локальный контейнер `mailhog`, перенаправляющий все исходящие письма в веб-панель MailHog. Для отправки реальных писем укажите параметры вашего SMTP-провайдера (например, Yandex/Google/Reg.ru).
