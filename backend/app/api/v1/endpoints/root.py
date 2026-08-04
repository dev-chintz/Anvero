from fastapi import APIRouter

router = APIRouter(tags=["Root"])


@router.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Welcome to Anvero API",
    }