# Адаптивный контроль знаний студентов

## Требования

Python 3.13.3. Команды ниже выполняются из папки проекта в PowerShell.

## Установка и первый запуск

Создайте виртуальное окружение и установите зависимости:

python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

Создайте конфигурацию и сгенерируйте секретный ключ:

Copy-Item .env.example .env
.\.venv\Scripts\python -c "from pathlib import Path; import secrets; p=Path('.env'); p.write_text(p.read_text().replace('replace-with-a-random-local-secret', secrets.token_urlsafe(50)), encoding='utf-8')"

Если файл `.env` уже настроен, пропустите его создание.

Примените миграции, загрузите демонстрационные данные и запустите сервер:

.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo
.\.venv\Scripts\python manage.py runserver --insecure

Откройте http://127.0.0.1:8000/. Для остановки сервера нажмите `Ctrl+C`.

Флаг `--insecure` используется для локальной отдачи CSS при `DEBUG=False`. Этот способ запуска предназначен для разработки и локальной демонстрации.

## Вход в систему

После выполнения `seed_demo` доступны учётные записи:

| Логин | Пароль | Роль |
| --- | --- | --- |
| `teacher` | `TeacherDemo2026!` | Преподаватель |
| `student1` | `StudentDemo2026!` | Студент |
| `student2` | `StudentDemo2026!` | Студент |

Эти пароли предназначены только для локальной демонстрации. Повторный запуск `seed_demo` не дублирует данные и не сбрасывает существующие пароли.

## Повторный запуск

.\.venv\Scripts\python manage.py runserver --insecure

Для работы в cmd замените `Copy-Item .env.example .env` на `copy .env.example .env`. Остальные приведённые команды совпадают.

В Linux и macOS используйте `python3.13 -m venv .venv`, путь `.venv/bin/python` вместо `.\.venv\Scripts\python` и `cp .env.example .env` для копирования конфигурации.
