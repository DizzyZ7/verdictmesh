from verdictmesh.domain import FillEstimate, OrderAction, OrderBookSnapshot


def estimate_fill(
    book: OrderBookSnapshot,
    action: OrderAction,
    amount: float,
) -> FillEstimate:
    """Estimate a taker fill by walking a recorded orderbook.

    For BUY, amount is quote notional in USDC. For SELL, amount is outcome-token quantity.
    """
    if amount <= 0:
        raise ValueError("amount must be positive")

    if action is OrderAction.BUY:
        levels = sorted(book.asks, key=lambda level: level.price)
        remaining = amount
        quantity = 0.0
        notional = 0.0
        worst_price: float | None = None

        for level in levels:
            capacity = level.price * level.size
            used_notional = min(capacity, remaining)
            if used_notional <= 0:
                continue
            quantity += used_notional / level.price
            notional += used_notional
            remaining -= used_notional
            worst_price = level.price
            if remaining <= 1e-12:
                break

        average_price = notional / quantity if quantity else None
        reference_price = book.best_ask
        slippage = None
        if average_price is not None and reference_price is not None:
            slippage = max(average_price - reference_price, 0.0)
        return FillEstimate(
            action=action,
            requested_amount=amount,
            filled_amount=notional,
            unfilled_amount=max(remaining, 0.0),
            quantity=quantity,
            notional=notional,
            average_price=average_price,
            worst_price=worst_price,
            reference_price=reference_price,
            slippage=slippage,
            fully_filled=remaining <= 1e-9,
        )

    levels = sorted(book.bids, key=lambda level: level.price, reverse=True)
    remaining = amount
    quantity = 0.0
    notional = 0.0
    worst_price = None

    for level in levels:
        used_quantity = min(level.size, remaining)
        if used_quantity <= 0:
            continue
        quantity += used_quantity
        notional += used_quantity * level.price
        remaining -= used_quantity
        worst_price = level.price
        if remaining <= 1e-12:
            break

    average_price = notional / quantity if quantity else None
    reference_price = book.best_bid
    slippage = None
    if average_price is not None and reference_price is not None:
        slippage = max(reference_price - average_price, 0.0)
    return FillEstimate(
        action=action,
        requested_amount=amount,
        filled_amount=quantity,
        unfilled_amount=max(remaining, 0.0),
        quantity=quantity,
        notional=notional,
        average_price=average_price,
        worst_price=worst_price,
        reference_price=reference_price,
        slippage=slippage,
        fully_filled=remaining <= 1e-9,
    )
