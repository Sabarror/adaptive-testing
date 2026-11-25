# Практическая №2: технические материалы

Работа выполнена в ветке `practice-2-testing` от
`b45d5c667cbaf7d1d2d89f6ecfebd3ca4b617dde`. Изменения локальные, push не выполнялся.
Это исходники тестов, результаты и материалы для самостоятельного оформления,
без титульного листа и формального учебного отчёта.

## Что получилось

* Исправлен реальный обработчик ошибок создания попытки: неожиданный IntegrityError
  больше не маскируется Attempt.DoesNotExist.
* Создание полного банка снимков переведено на bulk_create в прежней транзакции.
* Пройден **51 тест**: 34 прежних и 17 новых; Django check, проверка миграций,
  pip check и git diff --check успешны.
* Для 500 вопросов медиана start уменьшилась **164,863 → 85,043 мс (48,42%)**;
  для 2000 — **648,239 → 343,193 мс (47,06%)**, SQL-операции **2008 → 31**.
  Для 50 вопросов итоговый прогон показал **26,010 → 29,495 мс (замедление 13,40%)**.
  Память немного выросла. Отрицательные результаты сохранены наряду с ускорением.
* Разобраны D1/D3 — учебные ошибки границы/завершения; D2 — реальный недостаток
  передачи ошибки хранилища, подтверждённый управляемым нарушением UNIQUE.

## Навигация

| Материал | Файл |
|---|---|
| Исходное состояние, сверка DOCX с кодом, выбор объектов и стратегия | [strategy.md](strategy.md) |
| CFG, E/N/P, независимые пути и ограничения покрытия | [white-box.md](white-box.md) |
| Классы эквивалентности, BVA, причины/следствия, ограничения, решения | [black-box.md](black-box.md) |
| Реальные модули, stubs, drivers, два порядка интеграции | [integration.md](integration.md) |
| Три карточки отладки и воспроизведение | [defects.md](defects.md), [патчи](defects/) |
| Методика профилирования, оптимизация, риски ORM | [optimization.md](optimization.md) |
| Машинная таблица до/после | [benchmark-comparison.csv](results/benchmark-comparison.csv) |
| Таблицы с входом, ожиданием, путём, фактом и статусом | [white-box-results.csv](white-box-results.csv), [black-box-results.csv](black-box-results.csv) |
| Итоговая связь требований и проверок | [traceability.md](traceability.md) |
| Редактируемые диаграммы и SVG | [diagrams/](diagrams/) |
| Версии, хеши, coverage, профили, компактные логи | [results/](results/) |

CSV записаны в UTF-8 с BOM для импорта в Excel/Word. DOT и Mermaid — редактируемые
исходники. В `input-documents.json` сохранены имена и хеши прочитанных приложений;
полные документы и извлечённый учебный отчёт не копируются в репозиторий.

## Повторный запуск

Все команды выполняются из корня репозитория в PowerShell. Используйте Python
3.13.3 и зависимости из корневого README; существующие `.env` и базу не заменяйте.
Дополнительные инструменты (не обновляют зависимости приложения):

```powershell
.\.venv\Scripts\python -m pip install -r requirements-practice2.txt
```

### Тесты и покрытие

```powershell
$env:PRACTICE2_EVIDENCE = 'docs/practice-2/results/test-evidence.json'
.\.venv\Scripts\python tools/practice2_run.py docs/practice-2/results/final-tests.txt .\.venv\Scripts\python -m coverage run --branch --source=testing manage.py test --verbosity 2
Remove-Item Env:PRACTICE2_EVIDENCE
.\.venv\Scripts\python -m coverage json --include=testing/domain.py,testing/services.py -o docs/practice-2/results/coverage.json
.\.venv\Scripts\python tools/practice2_run.py docs/practice-2/results/coverage-summary.txt .\.venv\Scripts\python -m coverage report --include=testing/domain.py,testing/services.py
```

Test runner создаёт отдельную тестовую БД и удаляет её. В выполненных прогонах
это `file:memorydb_default?mode=memory&cache=shared`, что видно в логах. Если у вас
настроен TEST_DATABASE_PATH, убедитесь, что он указывает на отдельную тестовую БД.
Обычный запуск без измерения покрытия: `.\.venv\Scripts\python manage.py test`.

Для исходных тестов без переключения рабочей ветки можно выполнить
`manage.py test testing.tests`; это проверяет прежние 34 сценария на итоговом коде.
Сохранённый baseline-tests.txt получен на исходном коде **до** исправлений.
Не выдавайте повторный запуск на итоговом коде за восстановление исторического baseline.

### Отладочные демонстрации

```powershell
.\.venv\Scripts\python tools/practice2_run.py docs/practice-2/results/defects-run.txt .\.venv\Scripts\python -X utf8 tools/practice2_defects.py
```

Ожидается код 0 общего скрипта и для каждого D1–D3: before=1, after=0.
Дефекты включаются только в дочерних процессах; не применяйте учебные патчи
к рабочим файлам для обычного тестирования.

### Измерения и производные таблицы

```powershell
.\.venv\Scripts\python tools/practice2_run.py docs/practice-2/results/benchmark-baseline-run.txt .\.venv\Scripts\python -X utf8 tools/practice2_benchmark.py --variant baseline
.\.venv\Scripts\python tools/practice2_run.py docs/practice-2/results/benchmark-final-run.txt .\.venv\Scripts\python -X utf8 tools/practice2_benchmark.py --variant final
.\.venv\Scripts\python -X utf8 tools/practice2_artifacts.py
dot -Tsvg docs/practice-2/diagrams/answer-causes.dot -o docs/practice-2/diagrams/answer-causes.svg
```

Запускайте версии последовательно и дождитесь окончания каждой. Не запускайте
тесты одновременно с измерениями. Скрипт создаёт и очищает собственный временный
SQLite-файл; миграции и заполнение банка не затрагивают пользовательскую базу.
Проценты на другой машине могут отличаться. При новых измерениях обновите числа
в README/optimization.md по CSV; генератор не переписывает объяснительные тексты.
Git-объект исходного commit должен оставаться доступным локально.

Graphviz нужен только для перерисовки SVG: без dot исходники DOT сохраняются,
генератор пропускает SVG. Готовые SVG уже включены. pypdf использован для чтения
исходного PDF и не требуется для обычного запуска тестов.

### Проверки проекта

```powershell
.\.venv\Scripts\python tools/practice2_run.py docs/practice-2/results/django-check.txt .\.venv\Scripts\python manage.py check
.\.venv\Scripts\python tools/practice2_run.py docs/practice-2/results/migrations-check.txt .\.venv\Scripts\python manage.py makemigrations --check --dry-run
.\.venv\Scripts\python tools/practice2_run.py docs/practice-2/results/pip-check.txt .\.venv\Scripts\python -m pip check
git diff --check
.\.venv\Scripts\python tools/practice2_run.py docs/practice-2/results/artifact-audit.txt .\.venv\Scripts\python -X utf8 tools/practice2_verify_artifacts.py
```

`practice2_run.py` сохраняет UTF-8 stdout+stderr и соседний `.status.json` с
командой и exit_code, возвращая код исходной команды. Он устраняет неоднозначность
PowerShell, где вывод Django в stderr сам по себе мог выглядеть как ошибка запуска.

## Оставшиеся ограничения

Полный перебор циклических путей и всех внутренних исключений Django не выполнен.
Coverage имеет описанные ограничения для однострочных выражений; 100% проекта
не заявляется. Уровни 0/6 в белом ящике valid_bank проверяются пробами: реальная БД
запрещает такие строки. Визуальный браузер, промышленная нагрузка и другие СУБД не
проверялись. Пик tracemalloc — Python-аллокации, не RSS. Конкурентное начало попытки
проверено stub-сценарием; реальный конкурентный тест относится к отправке ответа.
На малом банке ускорение итоговым прогоном не подтверждено.
