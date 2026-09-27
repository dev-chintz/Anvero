"""CSV export of the non-invoiced sales report, with the columns the owner chooses and in the
order they choose them (`docs/DECISIONS.md`, "Export columns, chosen by the owner"): UTF-8 with a
BOM, so Excel opens Polish diacritics correctly, and every value guarded against being read as a
spreadsheet formula. Amounts use a comma decimal separator, matching the accountant's own earlier
report (`temp/`, an `orderReport-…_report.csv` read in this session: `Kwota` column, e.g. `62,69`).

The default set, without a `columns` choice, is the owner's own: a running number, the order's
date, the buyer's name, and the amount actually paid — not every field this module can resolve.
"""

import csv
import io
from dataclasses import dataclass
from decimal import Decimal

from app.models.order import AddressType, Order
from app.schemas.sales_report import SalesReportRow

# a leading =, +, @ or - opens a formula in Excel/LibreOffice/Sheets if the cell is not guarded
_FORMULA_PREFIXES = ("=", "+", "@", "-")


def _guarded(value: str) -> str:
    return f"'{value}" if value and value[0] in _FORMULA_PREFIXES else value


def _money(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.2f}".replace(".", ",")


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    # `index` is the row's 1-based position in the export, for "lp"; every other column reads
    # from the order and its already-classified row
    resolve: "callable[[int, Order, SalesReportRow], str]"


def _invoice(order: Order):
    return order.address(AddressType.INVOICE)


def _customer_name(_index: int, order: Order, _row: SalesReportRow) -> str:
    return " ".join(p for p in (order.customer_first_name, order.customer_last_name) if p)


def _invoice_address(_index: int, order: Order, _row: SalesReportRow) -> str:
    invoice = _invoice(order)
    if invoice is None:
        return ""
    city_line = " ".join(p for p in (invoice.postal_code, invoice.city) if p)
    return ", ".join(p for p in (invoice.street, city_line) if p)


# The catalog every export column is chosen from, in the order the picker groups them
# (`docs/DECISIONS.md`). Never widen this without updating the picker and the docs together.
COLUMNS: dict[str, Column] = {
    c.key: c
    for c in (
        Column("lp", "Lp.", lambda index, _order, _row: str(index)),
        Column("order_label", "Numer zamówienia", lambda _i, _o, row: row.order_label or row.order_external_id),
        Column("order_external_id", "Numer u marketplace'u", lambda _i, _o, row: row.order_external_id),
        Column("source", "Źródło", lambda _i, _o, row: row.source.value),
        Column("ordered_at", "Data zamówienia", lambda _i, _o, row: row.ordered_at.strftime("%d.%m.%Y")),
        Column("customer_login", "Login", lambda _i, _o, row: row.buyer_login or ""),
        Column("customer_name", "Imię i nazwisko", _customer_name),
        Column("customer_email", "E-mail", lambda _i, order, _row: order.customer_email or ""),
        Column("customer_phone", "Telefon", lambda _i, order, _row: order.customer_phone or ""),
        Column("invoice_company_name", "Nazwa firmy", lambda _i, order, _row: (_invoice(order).company_name if _invoice(order) else None) or ""),
        Column("invoice_tax_id", "NIP", lambda _i, order, _row: (_invoice(order).tax_id if _invoice(order) else None) or ""),
        Column("invoice_address", "Adres", _invoice_address),
        Column("amount_total", "Kwota zamówienia (razem)", lambda _i, order, _row: _money(order.total_amount)),
        Column("amount_paid", "Kwota zapłacona", lambda _i, order, _row: _money(order.paid_amount)),
        Column("currency", "Waluta", lambda _i, _o, row: row.currency),
        Column("category", "Kategoria", lambda _i, _o, row: row.category.value),
        Column("included", "Uwzględnione", lambda _i, _o, row: "tak" if row.included else "nie"),
        Column("reason", "Powód", lambda _i, _o, row: row.reason),
        Column("rule_id", "Reguła", lambda _i, _o, row: row.rule_id or ""),
    )
}

# what the owner asked for as the default, in this order (`docs/DECISIONS.md`)
DEFAULT_COLUMNS = ["lp", "ordered_at", "customer_name", "amount_paid"]


def resolve_columns(chosen: list[str] | None) -> list[Column]:
    """The chosen columns, in the order given; the default set when nothing was chosen.
    Raises `KeyError` (the endpoint turns it into a 422) naming the first key it does not know."""
    keys = chosen if chosen else DEFAULT_COLUMNS
    return [COLUMNS[key] for key in keys]


def to_csv(pairs: list[tuple[Order, SalesReportRow]], columns: list[Column]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([column.label for column in columns])
    for index, (order, row) in enumerate(pairs, start=1):
        writer.writerow([_guarded(column.resolve(index, order, row)) for column in columns])
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
