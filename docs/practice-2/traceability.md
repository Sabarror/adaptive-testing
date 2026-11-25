# Итоговая таблица выполнения и трассируемость

Все статусы относятся к рабочей версии с хешами в `results/source-manifest.json`.
Результаты baseline отдельно привязаны к исходному commit. Условия/проверки внутри
subTest не считаются отдельными test methods: общий итог — 51 метод, не сумма строк таблиц.

| ID | Пункт / требование | Проверка или реализация | Подтверждающий артефакт | Статус / границы |
|---|---|---|---|---|
| P2-01 | Прочитать источники и инструкции | README, PDF, DOCX, код/зависимости/старые тесты | strategy.md, input-documents.json | Выполнено; расхождение D2 явно отмечено |
| P2-02 | Исходные commit/окружение/тесты, отдельная ветка | baseline b45d5c6, 34 теста | baseline-tests.txt, environment.json | Выполнено; `.vscode/` сохранён |
| P2-03 | Выбор объектов и стратегия | 3 функции белого; 2 контракта чёрного; 4 модуля; start | strategy.md | Выполнено |
| P2-04 | CFG, узлы/рёбра, V=E−N+2P | 2,6,9 при оговорённой модели | diagrams/*.dot/*.svg, cfg-complexity.json | Выполнено; внутренности вызываемых функций не раскрыты |
| P2-05 | Независимые пути, входы, недостижимость | S1–S2, B1–B6, A1–A9; проверка ранга | white-box.md, white-box-results.csv | Выполнено в рамках модели; B4/B5 через probes |
| P2-06 | Операторы, ветви, отдельные условия | WhiteBoxTests, BlackBoxTests, fault injection | coverage.json, coverage-selected.json, test-evidence.json | Выполнено; ограничения сырых arcs не скрыты |
| P2-07 | Эквивалентность, границы, неверные типы/пропуски | TestForm и HTTP/service answer | black-box.md, black-box-results.csv | Выполнено: 0/1/2/4/5/6; 0/1/2/99/100/101; −1/0/1/2/3/4 |
| P2-08 | Причины/следствия, AND/OR/NOT, E/I/O/R/M | C1–C5, шесть сжатых правил | answer-causes.dot/svg, black-box.md | Выполнено; неприменимые ограничения объяснены |
| P2-09 | Отклонение без частичных изменений | Сравнение revision/current/state/снимков/ответов | test_answer_decision_table_and_rollback; test_database_error_translation_and_atomicity | PASS |
| P2-10 | Нисходящая интеграция | Views→Mock service, service→EngineStub | integration.md, IntegrationTests | PASS; явные заглушки, вызовы и ошибки |
| P2-11 | Восходящая интеграция | driver домена, bank_driver ORM, затем service/HTTP | integration.md, IntegrationTests | PASS; явные драйверы и сборка |
| P2-12 | Сравнить подходы | Реальные риски/дефекты, качественная трудоёмкость | integration.md | Выполнено; часы не выдумывались |
| P2-13 | Три дефекта с категориями | D1 граница; D2 хранение→сервис; D3 состояние | defects.md, defects/*.patch, D*-before/after.txt, defects.json | Выполнено; D1/D3 учебные, D2 реальный обработчик при инъекции отказа |
| P2-14 | Реальный инструмент локализации | traceback + sys.settrace line/exception/return | D*-before/after.txt | Выполнено; без утверждения о неиспользованном debugger |
| P2-15 | Измерить до/после время, память, операции, SQL | start; 50/500/2000; 1 прогрев/7 повторов | benchmark-*.json, comparison.csv, profile-*.txt | Выполнено; tracemalloc не RSS |
| P2-16 | ≥10–15% или обоснование | bulk_create; 48,42% на 500; 47,06% на 2000 | optimization.md, benchmark-comparison.csv | Достигнуто на увеличенных банках; на 50 замедление 13,40% |
| P2-17 | Сохранить выбор и воспроизводимость | Старые AlgorithmTests + новый driver/перестановка | final-tests.txt; behavior_sha256 до/после | PASS; сигнатуры равны на трёх размерах |
| P2-18 | Снимки, UNIQUE, атомарность, PK, сигналы | Snapshot tests, start rollback, ORM contract | testing/test_practice2.py, старые ScenarioTests | PASS; только текущие модели и SQLite |
| P2-19 | Материалы без полного отчёта, секретов и БД | Тексты, CSV/JSON, диаграммы, компактные логи | README.md и этот каталог | Выполнено; .venv/БД не добавлены |
| P2-20 | Итоговые тесты и проверки качества | 51 тест; Django check; migrations; pip; diff | final-tests.txt, django-check.txt, migrations-check.txt, pip-check.txt | PASS; отдельный линтер проектом не предусмотрен |
| P2-21 | Дефекты выключены, версия воспроизводима | Процессы, hash до/после; манифест | defects.json, source-manifest.json, README.md | Выполнено; локальные изменения не закоммичены и не опубликованы |

Дополнительные ограничения перечислены в README, white-box.md и optimization.md.
Пункты с ограничениями не интерпретируются как доказательство полного покрытия
проекта, всех потоков исключений или производственной надёжности.
