"""Reading and keeping the assortment (docs/CATALOG.md)."""

from collections.abc import Sequence

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import (
    CATEGORY_DIFFERENT,
    CatalogImage,
    CatalogItem,
    CatalogListing,
)
from app.models.order import OrderSource
from app.schemas.catalog import (
    CatalogCategories,
    CatalogCategoryNode,
    CatalogFlag,
    CatalogSort,
    CatalogStatusFilter,
)

ALLEGRO = OrderSource.ALLEGRO
ERLI = OrderSource.ERLI


def _is_current():
    """An offer Allegro still lists: part of the assortment."""
    return and_(CatalogItem.source == ALLEGRO, CatalogItem.gone_at.is_(None))


class CatalogRepository:
    def __init__(self, db: Session):
        self.db = db

    # ---- what the sync keeps ------------------------------------------------

    def items_by_offer(self) -> dict[str, CatalogItem]:
        """Every Allegro offer ever read, with its pictures and listings, by offer id."""
        rows = self.db.scalars(
            select(CatalogItem)
            .where(CatalogItem.source == ALLEGRO)
            .options(selectinload(CatalogItem.images), selectinload(CatalogItem.listings))
        )
        return {item.offer_id: item for item in rows}

    def pending_images(self) -> Sequence[CatalogImage]:
        """Pictures of current offers that have no copy recorded: the ones never downloaded first,
        then those that failed before."""
        return self.db.scalars(
            select(CatalogImage)
            .join(CatalogItem, CatalogItem.id == CatalogImage.item_id)
            .where(_is_current(), CatalogImage.file_name.is_(None))
            .order_by(CatalogImage.fetch_error.is_not(None), CatalogItem.name, CatalogImage.position)
        ).all()

    def recorded_images(self) -> Sequence[CatalogImage]:
        """Pictures of current offers whose copy is recorded, to find those whose file has gone."""
        return self.db.scalars(
            select(CatalogImage)
            .join(CatalogItem, CatalogItem.id == CatalogImage.item_id)
            .where(_is_current(), CatalogImage.file_name.is_not(None))
        ).all()

    # ---- what the page reads ------------------------------------------------

    def _filtered(self, q, category_id, status, flag):
        stmt = select(CatalogItem).where(CatalogItem.source == ALLEGRO)

        if status is CatalogStatusFilter.CURRENT:
            stmt = stmt.where(CatalogItem.gone_at.is_(None))
        elif status is CatalogStatusFilter.ACTIVE:
            stmt = stmt.where(CatalogItem.gone_at.is_(None), CatalogItem.status == "ACTIVE")
        elif status is CatalogStatusFilter.INACTIVE:
            stmt = stmt.where(CatalogItem.gone_at.is_(None), CatalogItem.status != "ACTIVE")
        elif status is CatalogStatusFilter.GONE:
            stmt = stmt.where(CatalogItem.gone_at.is_not(None))

        if q and q.strip():
            needle = q.strip().lower()
            stmt = stmt.where(
                or_(
                    func.lower(CatalogItem.name).contains(needle, autoescape=True),
                    func.lower(CatalogItem.sku).contains(needle, autoescape=True),
                    CatalogItem.offer_id.contains(needle, autoescape=True),
                )
            )
        if category_id:
            stmt = stmt.where(CatalogItem.category_ids.contains(f"|{category_id}|", autoescape=True))

        if flag is CatalogFlag.NO_IMAGE:
            stmt = stmt.where(~exists().where(CatalogImage.item_id == CatalogItem.id))
        elif flag is CatalogFlag.NO_SKU:
            stmt = stmt.where(CatalogItem.sku.is_(None))
        elif flag is CatalogFlag.NOT_ON_ERLI:
            stmt = stmt.where(
                ~exists().where(CatalogListing.item_id == CatalogItem.id, CatalogListing.source == ERLI)
            )
        elif flag is CatalogFlag.CATEGORY_DIFFERS:
            stmt = stmt.where(
                exists().where(
                    CatalogListing.item_id == CatalogItem.id, CatalogListing.category_match == CATEGORY_DIFFERENT
                )
            )
        return stmt

    def list_items(
        self,
        q: str | None,
        category_id: str | None,
        status: CatalogStatusFilter,
        flag: CatalogFlag | None,
        sort: CatalogSort,
        descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[CatalogItem], int]:
        stmt = self._filtered(q, category_id, status, flag)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        column = {
            CatalogSort.NAME: func.lower(CatalogItem.name),
            CatalogSort.PRICE: CatalogItem.price,
            CatalogSort.STOCK: CatalogItem.stock,
        }[sort]
        # an offer without a price or a stock goes last either way, as PostgreSQL would not do by itself
        order = (column.desc() if descending else column.asc()).nulls_last()
        rows = self.db.scalars(
            stmt.options(selectinload(CatalogItem.images), selectinload(CatalogItem.listings))
            .order_by(order, CatalogItem.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return rows, total

    def count(self, *conditions) -> int:
        return self.db.scalar(select(func.count()).select_from(CatalogItem).where(CatalogItem.source == ALLEGRO, *conditions)) or 0

    def summary_counts(self) -> dict[str, int]:
        current = CatalogItem.gone_at.is_(None)
        no_image = ~exists().where(CatalogImage.item_id == CatalogItem.id)
        on_erli = exists().where(CatalogListing.item_id == CatalogItem.id, CatalogListing.source == ERLI)
        differs = exists().where(
            CatalogListing.item_id == CatalogItem.id, CatalogListing.category_match == CATEGORY_DIFFERENT
        )
        images = (
            select(func.count(CatalogImage.id), func.count(CatalogImage.file_name))
            .join(CatalogItem, CatalogItem.id == CatalogImage.item_id)
            .where(_is_current())
        )
        images_total, images_local = self.db.execute(images).one()
        return {
            "total": self.count(current),
            "active": self.count(current, CatalogItem.status == "ACTIVE"),
            "inactive": self.count(current, CatalogItem.status != "ACTIVE"),
            "gone": self.count(CatalogItem.gone_at.is_not(None)),
            "no_image": self.count(current, no_image),
            "no_sku": self.count(current, CatalogItem.sku.is_(None)),
            "not_on_erli": self.count(current, ~on_erli),
            "category_differs": self.count(current, differs),
            "images_total": images_total,
            "images_local": images_local,
        }

    def categories(self) -> CatalogCategories:
        """The category tree of the current offers, each node counting its own offers and
        everything below it."""
        paths = self.db.scalars(select(CatalogItem.category_path).where(_is_current()))
        root: dict[str, dict] = {}
        uncategorized = 0
        for path in paths:
            if not path:
                uncategorized += 1
                continue
            level = root
            for step in path:
                node = level.setdefault(step["id"], {"id": step["id"], "name": step["name"], "count": 0, "children": {}})
                node["count"] += 1
                level = node["children"]

        def build(level: dict[str, dict]) -> list[CatalogCategoryNode]:
            nodes = [
                CatalogCategoryNode(id=n["id"], name=n["name"], count=n["count"], children=build(n["children"]))
                for n in level.values()
            ]
            return sorted(nodes, key=lambda n: n.name.casefold())

        return CatalogCategories(tree=build(root), uncategorized=uncategorized)
