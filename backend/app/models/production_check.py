from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductionCheck(Base):
    """A product on the "to make" list that has been made.

    Kept by the product's key (`sku:...`, `offer:...` or `name:...`, see
    app/services/production.py), not by an order: the list is the queue turned
    around by product, so one tick covers the product for every order that waits
    for it. `quantity` is how many the list asked for when it was ticked; the
    product counts as made only while the list still asks for no more than that,
    so an order that arrives later and raises the number brings it back.
    """

    __tablename__ = "production_checks"

    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    checked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
