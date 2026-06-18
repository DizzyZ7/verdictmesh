# VerdictMesh

> **Consensus before capital.**

VerdictMesh — автономная платформа для исследования prediction markets, формирования вероятностных прогнозов, управления риском и контролируемого исполнения сделок.

Проект строится как модульный монолит: сбор данных, аналитические агенты, расчет вероятности, риск-контур, paper trading, аудит и будущий исполнитель разделены на независимые модули, но разворачиваются единым приложением.

## Текущий статус

Система работает только в режиме **paper trading**. Реальное исполнение намеренно отключено до накопления проверяемой статистики, калибровки прогнозов, тестирования рисков и проверки доступности площадки для фактической юрисдикции пользователя.

Уже реализовано:

- FastAPI API;
- получение активных рынков через Polymarket Gamma API;
- нормализация цен YES/NO, ликвидности и идентификаторов токенов;
- детерминированный риск-модуль;
- paper-брокер и учет позиций;
- PostgreSQL-аудит рынков, прогнозов, решений и виртуальных ордеров;
- восстановление paper-портфеля после перезапуска;
- идемпотентное сохранение неизменившихся снимков рынка;
- Alembic-миграции;
- Docker Compose;
- тесты, lint, строгая типизация и GitHub Actions CI.

## Архитектура

```text
Polymarket / внешние источники
              ↓
       сбор и нормализация
              ↓
      фильтрация кандидатов
              ↓
   совет аналитических агентов
              ↓
  вероятностный consensus layer
              ↓
  детерминированный risk engine
              ↓
 paper broker / execution adapter
              ↓
 PostgreSQL audit + monitoring
```

Языковая модель не получает доступ к приватным ключам и не может обойти риск-модуль.

## Быстрый запуск

```bash
cp .env.example .env
docker compose up --build
```

После запуска:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`

Контейнер API автоматически применяет Alembic-миграции перед запуском приложения.

## Локальная разработка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
pytest
uvicorn verdictmesh.api:app --reload
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
pytest
uvicorn verdictmesh.api:app --reload
```

Без Docker по умолчанию используется локальная SQLite-база `verdictmesh.db`. В Docker Compose приложение подключается к PostgreSQL.

## API

```text
GET  /health
GET  /markets
POST /risk/evaluate
POST /paper/orders
GET  /paper/portfolio
GET  /audit/decisions
```

## Базовые ограничения риска

```text
Минимальный net edge:          7%
Минимальная confidence:       70%
Минимальная ликвидность:  $10 000
Максимальный spread:          2.5%
Одна позиция:                   1% банка
Общая экспозиция:              10% банка
Дневной лимит потерь:           2% банка
High resolution risk:        запрет
Live trading:                выключен
```

## Хранилище

PostgreSQL хранит:

- актуальные рынки;
- уникальные изменения состояния рынка;
- входные параметры каждого прогноза;
- контекст риск-оценки;
- одобренные и отклоненные решения;
- причины отклонения;
- paper-ордера;
- агрегированные позиции;
- остаток виртуального капитала.

Решение и соответствующий paper-ордер записываются одной транзакцией.

## Проверки

```bash
ruff check .
mypy src
pytest
DATABASE_URL=sqlite+pysqlite:///./migration-test.db alembic upgrade head
DATABASE_URL=sqlite+pysqlite:///./migration-test.db alembic downgrade base
```

## Следующие этапы

1. Непрерывный сбор стаканов и исторических снимков.
2. Реалистичный backtesting со spread, slippage и latency.
3. Сбор и ранжирование первичных источников.
4. Multi-agent forecasting council на Claude.
5. Калибровка вероятностей, Brier Score и attribution стратегий.
6. Веб-панель и операционные уведомления.
7. Изолированный исполнитель с обязательной проверкой geoblock.

## Важно

VerdictMesh — экспериментальное программное обеспечение. Prediction markets связаны с риском полной потери средств, вложенных в позицию. Проект не гарантирует доходность и должен использоваться только там, где доступ к площадке и торговля разрешены.
