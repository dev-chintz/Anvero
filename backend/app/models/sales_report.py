from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.order import OrderSource
from app.models.user import User


class SalesReportOverride(Base):
    """An operator's manual decision on one order for the non-invoiced sales report.

    Keyed like `BillingEntry.order_external_id` and `MessageThread.order_external_id`: by
    marketplace and its own order id, not Anvero's, so the same override still applies after a
    re-import and reaches a row read from an uploaded CSV as well as one read from Anvero's own
    orders. `RulesEngine.classify` only consults this when its own rules land on `MANUAL_REVIEW`
    or `OUT_OF_SCOPE`: a complete company invoice (`INV-001`) excludes an order automatically and
    is not open to override, the same as in the tool this was ported from (`BUSINESS_RULES.md`
    4.4, "Priorytet 1 jest automatyczny").
    """

    __tablename__ = "sales_report_overrides"
    __table_args__ = (
        UniqueConstraint("source", "order_external_id", name="uq_sales_report_overrides_source_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    source: Mapped[OrderSource] = mapped_column(Enum(OrderSource, native_enum=False, length=32), nullable=False)
    order_external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # INCLUDE or EXCLUDE; there is no third manual state, unlike the automatic MANUAL_REVIEW
    included: Mapped[bool] = mapped_column(nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_user: Mapped["User | None"] = relationship()

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
