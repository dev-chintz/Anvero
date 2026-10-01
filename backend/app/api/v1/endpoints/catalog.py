"""The assortment: the seller's Allegro offers, their pictures, and how they stand on Erli
(docs/CATALOG.md). Read only: nothing here changes an offer on a marketplace."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import require_permission
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.integrations.base import IntegrationNotConfigured
from app.models.catalog import CatalogItem
from app.models.order import OrderSource
from app.models.user import User
from app.models.user_permission import PermissionArea, PermissionLevel
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.catalog import (
    CatalogCategories,
    CatalogCostRead,
    CatalogCostWrite,
    CatalogFlag,
    CatalogImageRead,
    CatalogItemList,
    CatalogItemRead,
    CatalogListingRead,
    CatalogProgressRead,
    CatalogSort,
    CatalogStatusFilter,
    CatalogSummary,
    CatalogSyncStarted,
    CategoryStep,
    ChannelSalesRead,
)
from app.services import erli_settings
from app.services.allegro_sync import ImportAlreadyRunning
from app.services.catalog import catalog_progress, read_note, start_catalog_sync
from app.services.catalog_images import MEDIA_TYPES, ImageStore
from app.services.finance import FinanceService, OfferSales

# Seen with the orders' permission: whoever works the orders works from the assortment's pictures
# and stock too (DECISIONS.md, 2026-10-01).
router = APIRouter(
    prefix="/catalog", tags=["Assortment"], dependencies=[require_permission(PermissionArea.ORDERS)]
)
# The pictures are the one thing served without a login: an `<img>` cannot send one, the files are
# named by their hash, and they are public on Allegro anyway.
public_router = APIRouter(prefix="/catalog", tags=["Assortment"])

ALLEGRO_OFFER_URL = "https://allegro.pl/oferta/{offer_id}"


def _local_url(file_name: str | None) -> str | None:
    return f"/api/v1/catalog/images/{file_name}" if file_name else None


ZERO = Decimal("0.00")


def _channel(sales: OfferSales | None, unit_cost: Decimal | None) -> ChannelSalesRead:
    """One marketplace's sales of an offer, with the cost of the pieces when the offer has a cost."""
    if sales is None:
        zero_cost = ZERO if unit_cost is not None else None
        return ChannelSalesRead(quantity=0, orders=0, sales=ZERO, fees=ZERO, net=ZERO, cost=zero_cost, margin=ZERO)
    cost = (unit_cost * sales.quantity).quantize(ZERO) if unit_cost is not None else None
    return ChannelSalesRead(
        quantity=sales.quantity,
        orders=len(sales.orders),
        sales=sales.sales,
        fees=sales.fees,
        net=sales.net,
        cost=cost,
        margin=sales.net - (cost or ZERO),
    )


def _period(sales_days: int) -> tuple[date | None, date]:
    """The first and last day of the sales asked for: the last `sales_days` days up to today in the
    business timezone, or, for 0, everything held (the first is then None)."""
    today = datetime.now(ZoneInfo(settings.business_timezone)).date()
    return (today - timedelta(days=sales_days - 1) if sales_days else None), today


def _read(item: CatalogItem, sales: dict[tuple[OrderSource, str], OfferSales]) -> CatalogItemRead:
    images = [
        CatalogImageRead(position=image.position, url=image.url, local_url=_local_url(image.file_name))
        for image in item.images
    ]
    listing = next((entry for entry in item.listings if entry.source is OrderSource.ERLI), None)
    cover = images[0] if images else None
    on_erli = sales.get((OrderSource.ERLI, listing.external_id)) if listing else None
    return CatalogItemRead(
        id=item.id,
        offer_id=item.offer_id,
        name=item.name,
        sku=item.sku,
        price=item.price,
        currency=item.currency,
        stock=item.stock,
        status=item.status,
        gone=item.gone_at is not None,
        category_path=[CategoryStep(**step) for step in item.category_path],
        allegro_url=ALLEGRO_OFFER_URL.format(offer_id=item.offer_id),
        thumbnail_url=(cover.local_url or cover.url) if cover else None,
        images=images,
        erli=(
            CatalogListingRead(
                source=listing.source.value,
                external_id=listing.external_id,
                matched_by=listing.matched_by,
                price=listing.price,
                currency=listing.currency,
                stock=listing.stock,
                status=listing.status,
                category_path=[CategoryStep(**step) for step in listing.category_path],
                category_match=listing.category_match,
            )
            if listing
            else None
        ),
        unit_cost=item.unit_cost,
        cost_updated_at=item.cost_updated_at,
        sales_allegro=_channel(sales.get((OrderSource.ALLEGRO, item.offer_id)), item.unit_cost),
        sales_erli=_channel(on_erli, item.unit_cost) if listing else None,
    )


@router.get("/items", response_model=CatalogItemList)
def list_items(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=64),
    status_filter: CatalogStatusFilter = Query(default=CatalogStatusFilter.CURRENT, alias="status"),
    flag: CatalogFlag | None = None,
    sort: CatalogSort = CatalogSort.NAME,
    descending: bool = False,
    sales_days: int = Query(default=30, ge=0, le=3650),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Offers, by name unless asked otherwise. `category` is a category id at any depth: the
    offers in it and everything below it. `sales_days` is the period of the sales shown with each
    offer, the last so many days (0: everything held)."""
    date_from, date_to = _period(sales_days)
    sales = FinanceService(db).offer_sales(date_from or date(2000, 1, 1), date_to)
    repository = CatalogRepository(db)
    if sort in (CatalogSort.SOLD, CatalogSort.MARGIN):
        # worked out from the orders, so the database cannot order by it: every match is read,
        # ordered here and then paged
        every = repository.all_items(q, category, status_filter, flag)
        reads = [_read(row, sales) for row in every]

        def key(read: CatalogItemRead):
            channels = [read.sales_allegro] + ([read.sales_erli] if read.sales_erli else [])
            return sum(c.quantity for c in channels) if sort is CatalogSort.SOLD else sum((c.margin for c in channels), ZERO)

        reads.sort(key=key, reverse=descending)
        return CatalogItemList(items=reads[offset : offset + limit], total=len(reads), sales_from=date_from)
    rows, total = repository.list_items(q, category, status_filter, flag, sort, descending, limit, offset)
    return CatalogItemList(items=[_read(row, sales) for row in rows], total=total, sales_from=date_from)


@router.put(
    "/items/{item_id}/cost",
    response_model=CatalogCostRead,
    dependencies=[require_permission(PermissionArea.ORDERS, PermissionLevel.MANAGE)],
)
def set_cost(
    item_id: uuid.UUID,
    body: CatalogCostWrite,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Say what making one piece of the offer costs (or take the cost away with null). The margin of
    the offer is worked out from it; a sync never changes it."""
    item = db.get(CatalogItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    item.unit_cost = body.unit_cost
    item.cost_updated_at = datetime.now(UTC) if body.unit_cost is not None else None
    item.cost_updated_by_user_id = current_user.id if body.unit_cost is not None else None
    db.commit()
    return CatalogCostRead(id=item.id, unit_cost=item.unit_cost, cost_updated_at=item.cost_updated_at)


@router.get("/categories", response_model=CatalogCategories)
def categories(db: Session = Depends(get_db)):
    return CatalogRepository(db).categories()


@router.get("/summary", response_model=CatalogSummary)
def summary(db: Session = Depends(get_db)):
    note = read_note(db)
    return CatalogSummary(
        **CatalogRepository(db).summary_counts(),
        erli_unmatched=note.erli_unmatched if note else None,
        erli_connected=erli_settings.build_erli_client(db).is_configured,
        last_sync=note,
    )


@router.get("/progress", response_model=CatalogProgressRead)
def progress():
    """Where the sync that is running has got to, whoever started it (the button or the schedule)."""
    return CatalogProgressRead(
        running=catalog_progress.running,
        phase=catalog_progress.phase,
        done=catalog_progress.done,
        total=catalog_progress.total,
        started_at=catalog_progress.started_at,
    )


@router.post(
    "/sync",
    response_model=CatalogSyncStarted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[require_permission(PermissionArea.ORDERS, PermissionLevel.MANAGE)],
)
@limiter.limit("6/minute")
def sync(request: Request, db: Session = Depends(get_db)):
    """Start reading the offers from Allegro (and checking Erli's products against them) and return
    at once: it takes minutes. `GET /catalog/progress` says how far it has got, `GET /catalog/summary`
    how it ended.

    Shares the import lock with an order import, since both use the same rotating token.
    """
    try:
        start_catalog_sync(db)
    except ImportAlreadyRunning as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An Allegro import or sync is already running"
        ) from exc
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Allegro is not configured") from exc
    return CatalogSyncStarted()


@public_router.get("/images/{file_name}", include_in_schema=True)
def image(file_name: str):
    """A stored picture. The name is the hash of its bytes, so it never changes and may be cached
    for good."""
    path = ImageStore().path_for(file_name)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Picture not found")
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[file_name.rsplit(".", 1)[1]],
        headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
    )
