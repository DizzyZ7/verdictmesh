# VerdictMesh

> **Consensus before capital.**

VerdictMesh — автономная платформа для исследования prediction markets, формирования вероятностных прогнозов, управления риском и контролируемого исполнения сделок.

Проект строится как модульный монолит: сбор данных, аналитические агенты, расчет вероятности, риск-контур, paper trading, аудит и будущий исполнитель разделены на независимые модули, но разворачиваются единым приложением.

## Текущий статус

Система работает только в режиме **paper trading**. Реальное исполнение намеренно отключено до накопления проверяемой статистики, калибровки прогнозов, тестирования рисков и проверки доступности площадки для фактической юрисдикции пользователя.

Уже реализовано:

- FastAPI API с операторской API-key авторизацией;
- получение активных рынков через Polymarket Gamma API;
- автономный polling публичных CLOB-стаканов;
- сохранение полной глубины bids/asks и hash состояния;
- расчет best bid, best ask, midpoint, spread и доступного notional;
- симуляция BUY/SELL по глубине стакана с учетом slippage и неполного исполнения;
- автономный сбор и ранжирование evidence через GDELT DOC API;
- evidence-grounded council из четырех независимых Claude-ролей;
- schema-constrained JSON для всех ответов моделей;
- детерминированный consensus с disagreement, confidence interval и evidence coverage;
- fail-closed запреты при слабых источниках, высокой неопределенности или неясных правилах;
- детерминированный риск-модуль;
- paper-брокер и учет позиций;
- PostgreSQL-аудит рынков, evidence, прогнозов, решений, стаканов и виртуальных ордеров;
- восстановление paper-портфеля после перезапуска;
- liveness и readiness probes;
- Prometheus-совместимые HTTP и runtime-метрики;
- JSON-логи с request ID, route template, статусом и latency;
- Alembic-миграции;
- non-root Docker image с healthcheck;
- тесты, lint, строгая типизация и GitHub Actions CI.

## Архитектура

```text
Gamma API + CLOB orderbooks + GDELT / внешние источники
                              ↓
                   сбор и нормализация
                              ↓
                  историческое хранилище
                              ↓
                  фильтрация кандидатов
                              ↓
       researcher + domain expert + skeptic + resolution auditor
                              ↓
            deterministic probability consensus
                              ↓
              детерминированный risk engine
                              ↓
             paper broker / execution adapter
                              ↓
        PostgreSQL audit + metrics + structured logs
```

Языковая модель не получает доступ к приватным ключам и не может обойти consensus или risk engine.

## Быстрый запуск

```bash
cp .env.example .env
docker compose up --build
```

После запуска:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`
- liveness: `http://localhost:8000/health`
- readiness: `http://localhost:8000/ready`

Контейнер API автоматически применяет Alembic-миграции. При `ORDER_BOOK_SCANNER_ENABLED=true` исторический сбор начинается автоматически после запуска.

Для реального вызова forecast council добавь `ANTHROPIC_API_KEY` в `.env`. Детерминированный endpoint `/forecast/consensus` работает без внешнего API и полезен для тестирования схем и aggregation logic.

## Операторская авторизация

При наличии `OPERATOR_API_KEY` все рабочие маршруты требуют заголовок `X-API-Key`. Публичными остаются `/health`, `/ready`, `/docs`, `/redoc` и `/openapi.json`.

```env
APP_ENV=production
OPERATOR_API_KEY=<случайный секрет длиной не менее 32 символов>
OPERATOR_API_KEY_HEADER=X-API-Key
```

```bash
curl -H "X-API-Key: $OPERATOR_API_KEY" http://localhost:8000/markets
```

`production` и `staging` завершаются fail-fast, если операторский ключ не задан.

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
GET  /ready
GET  /metrics
GET  /markets
POST /scanner/orderbooks
GET  /history/orderbooks/{asset_id}
POST /backtest/fill
POST /evidence/collect
GET  /evidence/packages
POST /forecast/consensus
POST /forecast/run
POST /forecast/auto
GET  /forecast/runs
POST /risk/evaluate
POST /paper/orders
GET  /paper/portfolio
GET  /audit/decisions
```

Для `POST /backtest/fill` поле `amount` означает сумму USDC при `BUY` и количество outcome-токенов при `SELL`.

## Health и observability

`GET /health` — только liveness. Он не обращается к PostgreSQL и подтверждает, что процесс способен отвечать по HTTP.

`GET /ready` — readiness. Он проверяет доступ к базе и состояние обязательного фонового CLOB-сканера. При неготовности возвращается HTTP 503.

`GET /metrics` — Prometheus text format. Endpoint защищается операторским ключом, когда авторизация включена. Метрики включают:

- количество HTTP-запросов по method, route template и status;
- суммарную длительность и количество измеренных запросов;
- число запросов in-flight;
- время запуска процесса;
- состояние CLOB-сканера;
- число ошибок фонового сканера;
- timestamp последнего успешного цикла.

Динамические значения URL не используются как labels: например, все запросы истории агрегируются под `/history/orderbooks/{asset_id}`.

Логи настраиваются через:

```env
LOG_LEVEL=INFO
LOG_FORMAT=json
```

JSON-лог HTTP-запроса содержит `request_id`, `method`, `route`, `status_code`, `duration_ms` и адрес клиента. Для локальной разработки можно использовать `LOG_FORMAT=text`.

## Forecast council

Каждый прогноз формируют четыре независимые роли:

```text
researcher            — собирает факты, base rates и прямые доказательства
domain_expert         — применяет отраслевую экспертизу и causal reasoning
skeptic               — ищет контраргументы, bias и скрытые допущения
resolution_auditor    — проверяет точную формулировку и источник resolution
```

Текущая цена рынка намеренно не передается агентам, чтобы снизить anchoring. После получения четырех ответов обычный код рассчитывает:

- итоговую вероятность YES;
- доверительный интервал;
- disagreement между агентами;
- coverage и качество доказательств;
- resolution clarity;
- raw edge относительно цены рынка;
- причины `NO TRADE`.

Forecast автоматически запрещается, когда агент ссылается на неизвестный evidence ID, отсутствует resolution auditor, доказательств недостаточно, disagreement слишком высок или edge ниже порога.

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
- входные evidence и правила resolution;
- версии моделей и ответы каждого агента;
- итоговые council forecasts и причины `NO TRADE`;
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
docker build -t verdictmesh:local .
```

## Следующие этапы

1. WebSocket-поток CLOB и восстановление стакана по incremental updates.
2. Replay engine с latency, fees, spread и разрешением рынка.
3. Калибровка вероятностей, Brier Score и attribution стратегий.
4. Retention policy и архивирование исторических данных.
5. Веб-панель и операционные уведомления.
6. Изолированный исполнитель с обязательной проверкой geoblock.

## Важно

VerdictMesh — экспериментальное программное обеспечение. Prediction markets связаны с риском полной потери средств, вложенных в позицию. Проект не гарантирует доходность и должен использоваться только там, где доступ к площадке и торговля разрешены.
