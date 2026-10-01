"""The assortment: the seller's Allegro offers, their pictures, and how they stand on Erli
(docs/CATALOG.md). Read only: nothing here changes an offer on a marketplace."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.models.catalog import CatalogItem
from app.models.order import OrderSource
from app.models.user_permission import PermissionArea, PermissionLevel
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.catalog import (
    CatalogCategories,
    CatalogFlag,
    CatalogImageRead,
    CatalogItemList,
    CatalogItemRead,
    CatalogListingRead,
    CatalogSort,
    CatalogStatusFilter,
    CatalogSummary,
    CatalogSyncRead,
    CategoryStep,
)
from app.services import erli_settings
from app.services.allegro_sync import ImportAlreadyRunning
from app.services.catalog import read_note, run_catalog_sync
from app.services.catalog_images import MEDIA_TYPES, ImageStore

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


def _read(item: CatalogItem) -> CatalogItemRead:
    images = [
        CatalogImageRead(position=image.position, url=image.url, local_url=_local_url(image.file_name))
        for image in item.images
    ]
    listing = next((entry for entry in item.listings if entry.source is OrderSource.ERLI), None)
    cover = images[0] if images else None
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
    )


@router.get("/items", response_model=CatalogItemList)
def list_items(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=64),
    status_filter: CatalogStatusFilter = Query(default=CatalogStatusFilter.CURRENT, alias="status"),
    flag: CatalogFlag | None = None,
    sort: CatalogSort = CatalogSort.NAME,
    descending: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Offers, by name unless asked otherwise. `category` is a category id at any depth: the
    offers in it and everything below it."""
    rows, total = CatalogRepository(db).list_items(
        q, category, status_filter, flag, sort, descending, limit, offset
    )
    return CatalogItemList(items=[_read(row) for row in rows], total=total)


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


@router.post(
    "/sync",
    response_model=CatalogSyncRead,
    dependencies=[require_permission(PermissionArea.ORDERS, PermissionLevel.MANAGE)],
)
@limiter.limit("6/minute")
def sync(request: Request, db: Session = Depends(get_db)):
    """Read the offers from Allegro now (and check Erli's products against them).

    Shares the import lock with an order import, since both use the same rotating token.
    """
    try:
        result = run_catalog_sync(db)
    except ImportAlreadyRunning as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An Allegro import or sync is already running"
        ) from exc
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Allegro is not configured") from exc
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return CatalogSyncRead(
        items=result.items,
        added=result.added,
        gone=result.gone,
        images_downloaded=result.images_downloaded,
        images_failed=result.images_failed,
        images_pending=result.images_pending,
        erli_products=result.erli_products,
        erli_matched=result.erli_matched,
        erli_unmatched=result.erli_unmatched,
        erli_error=result.erli_error,
        details_failed=result.details_failed,
    )


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
