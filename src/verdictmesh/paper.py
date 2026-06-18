from verdictmesh.domain import PaperOrder, PaperPosition, RiskDecision, TradeProposal


class PaperBroker:
    def __init__(self, starting_cash: float) -> None:
        if starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        self._starting_cash = starting_cash
        self._cash = starting_cash
        self._orders: list[PaperOrder] = []
        self._positions: dict[str, PaperPosition] = {}

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def exposure(self) -> float:
        return sum(position.cost_basis for position in self._positions.values())

    def submit(self, proposal: TradeProposal, decision: RiskDecision) -> PaperOrder:
        if not decision.approved:
            raise ValueError("risk decision rejected the trade")
        if decision.approved_stake > self._cash:
            raise ValueError("insufficient paper cash")

        quantity = decision.approved_stake / proposal.entry_price
        order = PaperOrder(
            market_id=proposal.market_id,
            side=proposal.side,
            price=proposal.entry_price,
            stake=decision.approved_stake,
            quantity=quantity,
        )
        self._cash -= order.stake
        self._orders.append(order)
        self._apply_fill(order)
        return order

    def snapshot(self) -> dict[str, object]:
        return {
            "starting_cash": self._starting_cash,
            "cash": self._cash,
            "exposure": self.exposure,
            "orders": [order.model_dump(mode="json") for order in self._orders],
            "positions": [
                position.model_dump(mode="json") for position in self._positions.values()
            ],
        }

    def mark_to_market(self, prices: dict[str, float]) -> float:
        market_value = 0.0
        for key, position in self._positions.items():
            price = prices.get(key, position.average_price)
            if not 0 <= price <= 1:
                raise ValueError("mark price must be between 0 and 1")
            market_value += position.quantity * price
        return self._cash + market_value

    def _apply_fill(self, order: PaperOrder) -> None:
        key = f"{order.market_id}:{order.side.value}"
        existing = self._positions.get(key)
        if existing is None:
            self._positions[key] = PaperPosition(
                market_id=order.market_id,
                side=order.side,
                quantity=order.quantity,
                average_price=order.price,
                cost_basis=order.stake,
            )
            return

        quantity = existing.quantity + order.quantity
        cost_basis = existing.cost_basis + order.stake
        self._positions[key] = PaperPosition(
            market_id=order.market_id,
            side=order.side,
            quantity=quantity,
            average_price=cost_basis / quantity,
            cost_basis=cost_basis,
        )
