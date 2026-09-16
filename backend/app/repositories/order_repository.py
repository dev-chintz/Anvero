import uuid

from sqlalchemy.orm import Session

from app.models.order import Order, OrderSource, OrderStatus


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, order: Order) -> Order:
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get(self, order_id: uuid.UUID) -> Order | None:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def list_all(self, skip: int = 0, limit: int = 100) -> list[Order]:
        return (
            self.db.query(Order)
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def list_by_source(
        self, source: OrderSource, skip: int = 0, limit: int = 100
    ) -> list[Order]:
        return (
            self.db.query(Order)
            .filter(Order.source == source)
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def list_by_status(
        self, status: OrderStatus, skip: int = 0, limit: int = 100
    ) -> list[Order]:
        return (
            self.db.query(Order)
            .filter(Order.status == status)
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count(
        self,
        source: OrderSource | None = None,
        status: OrderStatus | None = None,
    ) -> int:
        query = self.db.query(Order)
        if source is not None:
            query = query.filter(Order.source == source)
        if status is not None:
            query = query.filter(Order.status == status)
        return query.count()
