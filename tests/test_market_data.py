from verdictmesh.market_data import normalize_markets


def test_normalize_gamma_market() -> None:
    events = [
        {
            "title": "Example event",
            "slug": "example-event",
            "markets": [
                {
                    "id": "123",
                    "question": "Will the example happen?",
                    "conditionId": "0xabc",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.62", "0.38"]',
                    "clobTokenIds": '["yes-token", "no-token"]',
                    "liquidityNum": 20_000,
                    "volume24hr": 5_000,
                    "active": True,
                    "closed": False,
                }
            ],
        }
    ]

    snapshots = normalize_markets(events)

    assert len(snapshots) == 1
    assert snapshots[0].price_yes == 0.62
    assert snapshots[0].price_no == 0.38
    assert snapshots[0].token_id_yes == "yes-token"
