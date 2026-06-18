# VerdictMesh

> **Consensus before capital.**

VerdictMesh — автономная платформа для исследования prediction markets, формирования вероятностных прогнозов, управления риском и контролируемого исполнения сделок.

Проект строится как модульный монолит: сбор данных, аналитические агенты, расчет вероятности, риск-контур, paper trading, аудит и будущий исполнитель разделены на независимые модули, но разворачиваются единым приложением.

## Текущий статус

Система работает только в режиме **paper trading**. Реальное исполнение намеренно отключено до накопления проверяемой статистики, калибровки прогнозов, тестирования рисков и проверки доступности площадки для фактической юрисдикции пользователя.

Уже реализовано:

- FastAPI API;
- получение активных рынков через Polymarket Gamma API;
- автономный polling публичных CLOB-стаканов;
- сохранение полной глубины bids/asks и hash состояния;
- расчет best bid, best ask, midpoint, spread и доступного notional;
- симуляция BUY/SELL по глубине стакана с учетом slippage и неполного исполнения;
- детерминированный риск-модуль;
- paper-брокер и учет позиций;
- PostgreSQL-аудит рынков, прогнозов, решений, стаканов и виртуальных ордеров;
- восстановление paper-портфеля после перезапуска;
- идемпотентное сохранение неизменившихся снимков;
- Alembic-миграции;
- Docker Compose;
- тесты, lint, строгая типизация и GitHub Actions CI.

## Архитектура

```text
Gamma API + CLOB orderbooks + внешние источники
                        ↓
             сбор и нормализация
                        ↓
            историческое хранилище
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

Контейнер API автоматически применяет Alembic-миграции. При `ORDER_BOOK_SCANNER_ENABLED=true` исторический сбор начинается автоматически после запуска.

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
POST /scanner/orderbooks
GET  /history/orderbooks/{asset_id}
POST /backtest/fill
POST /risk/evaluate
POST /paper/orders
GET  /paper/portfolio
GET  /audit/decisions
```

Для `POST /backtest/fill` поле `amount` означает сумму USDC при `BUY` и количество outcome-токенов при `SELL`.

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

## Исторический scanner

Настройки:

```text
ORDER_BOOK_SCANNER_ENABLED=true
ORDER_BOOK_SCAN_INTERVAL_SECONDS=60
ORDER_BOOK_SCAN_CONCURRENCY=10
ORDER_BOOK_MARKET_LIMIT=50
ORDER_BOOK_ASSET_LIMIT=100
```

Одинаковый стакан повторно не записывается: уникальность определяется сочетанием `asset_id` и CLOB `book_hash`.

## Хранилище

PostgreSQL хранит:

- актуальные рынки;
- изменения рыночных цен;
- полную глубину исторических стаканов;
- top-of-book и рассчитанные метрики ликвидности;
- входные параметры каждого прогноза;
- контекст риск-оценки;
- одобренные и отклоненные решения;
- paper-ордера, позиции и остаток виртуального капитала.

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

1. WebSocket-поток CLOB и восстановление стакана по incremental updates.
2. Replay engine с latency, fees, spread и разрешением рынка.
3. Сбор и ранжирование первичных источников.
4. Multi-agent forecasting council на Claude.
5. Калибровка вероятностей, Brier Score и attribution стратегий.
6. Веб-панель и операционные уведомления.
7. Изолированный исполнитель с обязательной проверкой geoblock.

## Важно

VerdictMesh — экспериментальное программное обеспечение. Prediction markets связаны с риском полной потери средств, вложенных в позицию. Проект не гарантирует доходность и должен использоваться только там, где доступ к площадке и торговля разрешены.
