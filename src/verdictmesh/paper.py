from verdictmesh.domain import PaperOrder, PaperPosition, RiskDecision, TradeProposal


class PaperBroker:
    def __init__(self, starting_cash: float) -> None:
        if starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        self._starting_cash = starting_cash
        self._cash = starting_cash
        self._orders: list[PaperOrder] = []
        self._positions: dict[str, PaperPosition] = {}

    @classmethod
    def restore(
        cls,
        *,
        starting_cash: float,
        cash: float,
        orders: list[PaperOrder],
        positions: list[PaperPosition],
    ) -> "PaperBroker":
        broker = cls(starting_cash)
        if cash < 0:
            raise ValueError("restored cash cannot be negative")
        broker._cash = cash
        broker._orders = list(orders)
        broker._positions = {
            broker.position_key(position.market_id, position.side.value): position
            for position in positions
        }
        return broker

    @staticmethod
    def position_key(market_id: str, side: str) -> str:
        return f"{market_id}:{side}"

    @property
    def starting_cash(self) -> float:
        return self._starting_cash

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def exposure(self) -> float:
        return sum(position.cost_basis for position in self._positions.values())

    def prepare_order(self, proposal: TradeProposal, decision: RiskDecision) -> PaperOrder:
        if not decision.approved:
            raise ValueError("risk decision rejected the trade")
        if decision.approved_stake > self._cash:
            raise ValueError("insufficient paper cash")
        return PaperOrder(
            market_id=proposal.market_id,
            side=proposal.side,
            price=proposal.entry_price,
            stake=decision.approved_stake,
            quantity=decision.approved_stake / proposal.entry_price,
        )

    def projected_position(self, order: PaperOrder) -> PaperPosition:
        key = self.position_key(order.market_id, order.side.value)
        existing = self._positions.get(key)
        if existing is None:
            return PaperPosition(
                market_id=order.market_id,
                side=order.side,
                quantity=order.quantity,
                average_price=order.price,
                cost_basis=order.stake,
            )

        quantity = existing.quantity + order.quantity
        cost_basis = existing.cost_basis + order.stake
        return PaperPosition(
            market_id=order.market_id,
            side=order.side,
            quantity=quantity,
            average_price=cost_basis / quantity,
            cost_basis=cost_basis,
        )

    def apply_order(self, order: PaperOrder) -> None:
        if order.stake > self._cash:
            raise ValueError("insufficient paper cash")
        self._cash -= order.stake
        self._orders.append(order)
        position = self.projected_position(order)
        key = self.position_key(order.market_id, order.side.value)
        self._positions[key] = position

    def submit(self, proposal: TradeProposal, decision: RiskDecision) -> PaperOrder:
        order = self.prepare_order(proposal, decision)
        self.apply_order(order)
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
