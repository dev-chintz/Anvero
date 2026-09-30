"""The non-invoiced sales record (docs/NON_INVOICED_SALES.md, sections 4b, 4d and 4h): the
product flag for goods excluded from the exemption, and the ledger itself."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.order import PAYMENT_TYPE, OrderSource, PaymentType
from app.models.user import User

SOURCE = Enum(OrderSource, native_enum=False, length=32)


class ProductSetting(Base):
    """What the owner has said about one product (one marketplace offer).

    For now one thing: that the goods are on the list of § 4 ust. 1 pkt 1 of the regulation and so
    can never use the poz. 41 exemption, whatever else is true of the sale (NON_INVOICED_SALES.md,
    section 4h). Off unless someone turns it on; no row means off.
    """

    __tablename__ = "product_settings"
    __table_args__ = (UniqueConstraint("source", "offer_id", name="uq_product_settings_source_offer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[OrderSource] = mapped_column(SOURCE, nullable=False)
    # the marketplace's id of the listing, as order_items.offer_id holds it
    offer_id: Mapped[str] = mapped_column(String(255), nullable=False)

    excluded_from_exemption: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class LedgerKind(str, enum.Enum):
    # money received: an order's main payment, or one of its surcharges
    SALE = "SALE"
    # money returned (a refund, or a refund's cancelling), or a sale moved in or out of the report
    # after the report holding it was handed over
    CORRECTION = "CORRECTION"


# how a payment was tied to the payout that took it to the bank (4d)
PAYOUT_FIRST_AFTER = "FIRST_AFTER"


class LedgerEntry(Base):
    """One money event of the non-invoiced sales record (docs/NON_INVOICED_SALES.md, 4b).

    Not a view over the orders: an order changes (a re-import, a refund, a buyer's data erased), and
    a report already handed over must not change with it. So what the record must show is copied
    here when the row is written: the amount, the date, the buyer and their address. After that only
    the classification of a row that is not locked follows the order (app/services/non_invoiced/
    ledger.py); a locked row is never changed, and what would have changed it becomes a correction.
    """

    __tablename__ = "non_invoiced_ledger"
    __table_args__ = (UniqueConstraint("source", "event_key", name="uq_non_invoiced_ledger_source_event_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    kind: Mapped[LedgerKind] = mapped_column(Enum(LedgerKind, native_enum=False, length=16), nullable=False)
    # What makes the event one, so that writing it again finds it: `ORDER:<id>` for an order's main
    # payment, `SURCHARGE:<id>` for a surcharge, `OPERATION:<fingerprint>` for a refund's operation,
    # `RECLASSIFIED:<sale row>:<n>` for the n-th move of a locked sale in or out of the report.
    event_key: Mapped[str] = mapped_column(String(160), nullable=False)

    # when it happened, in UTC, and that moment's calendar day in the business timezone: for a sale
    # the payment's time (the accountant: the payment date decides the period), for a refund the
    # operation's, for a reclassification when it was found
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    source: Mapped[OrderSource] = mapped_column(SOURCE, nullable=False)
    # the order; kept if the order row ever goes, since the record must outlive it
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True, nullable=True
    )
    order_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # the sale a correction corrects
    corrects_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("non_invoiced_ledger.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # gross and signed: a sale positive, money returned negative
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # the buyer as the order named them when the row was written, with their own address (poz. 41:
    # "dane nabywcy, w tym jego adres"); erased by retention, not by a buyer's own request
    # (docs/GDPR.md)
    buyer_first_name: Mapped[str | None] = mapped_column(String(255))
    buyer_last_name: Mapped[str | None] = mapped_column(String(255))
    buyer_street: Mapped[str | None] = mapped_column(String(255))
    buyer_postal_code: Mapped[str | None] = mapped_column(String(32))
    buyer_city: Mapped[str | None] = mapped_column(String(255))
    buyer_country_code: Mapped[str | None] = mapped_column(String(8))
    # set when retention erased the buyer fields above
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # the trace of the money: how it was paid and through whom, the marketplace's payment id (or
    # the surcharge's), the payment operation it was matched to, and the payout that took it to the
    # bank account (4d)
    payment_type: Mapped[PaymentType | None] = mapped_column(PAYMENT_TYPE)
    payment_operator: Mapped[str | None] = mapped_column(String(64))
    payment_id: Mapped[str | None] = mapped_column(String(64), index=True)
    operation_fingerprint: Mapped[str | None] = mapped_column(String(64))
    payout_id: Mapped[str | None] = mapped_column(String(64))
    payout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # how the payout was found: FIRST_AFTER, the first payout of the same wallet after the payment
    payout_link: Mapped[str | None] = mapped_column(String(16))

    # the classifier's result (app/services/non_invoiced/classifier.py); for a correction, the
    # category whose total it adjusts
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(48), nullable=False)
    ruleset: Mapped[str] = mapped_column(String(32), nullable=False)

    # a person's decision, beside the automatic result rather than replacing it; never on a
    # company's sale, never on a locked row
    override_category: Mapped[str | None] = mapped_column(String(32))
    override_note: Mapped[str | None] = mapped_column(Text)
    overridden_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overridden_by: Mapped["User | None"] = relationship(foreign_keys=[overridden_by_user_id])

    # set when a report holding the row was handed over to the accountant; the row never changes
    # after it
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
