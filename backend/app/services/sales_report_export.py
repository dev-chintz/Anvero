"""CSV export of the non-invoiced sales report, in the shape the ported tool used
(`docs/DECISIONS.md`): UTF-8 with a BOM, so Excel opens Polish diacritics correctly, and every
value guarded against being read as a spreadsheet formula.

Only the columns accounting needs: no address or phone, matching `ROADMAP.md`'s GDPR to-do
(point 4, keep the report's personal data to what it needs)."""

import csv
import io

from app.schemas.sales_report import SalesReportList

# a leading =, +, @ or - opens a formula in Excel/LibreOffice/Sheets if the cell is not guarded
_FORMULA_PREFIXES = ("=", "+", "@", "-")


def _guarded(value: str) -> str:
    return f"'{value}" if value and value[0] in _FORMULA_PREFIXES else value


def to_csv(report: SalesReportList) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Zamówienie", "Źródło", "Data", "Kupujący", "Kwota", "Waluta", "Kategoria", "Uwzględnione", "Powód", "Reguła"]
    )
    for row in report.items:
        writer.writerow(
            [
                _guarded(row.order_label or row.order_external_id),
                row.source.value,
                row.ordered_at.date().isoformat(),
                _guarded(row.buyer_login or ""),
                f"{row.amount:.2f}",
                row.currency,
                row.category.value,
                "tak" if row.included else "nie",
                _guarded(row.reason),
                row.rule_id or "",
            ]
        )
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
