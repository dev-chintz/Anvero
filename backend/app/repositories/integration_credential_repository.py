from sqlalchemy.orm import Session

from app.models.integration import IntegrationCredential


class IntegrationCredentialRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, provider: str) -> IntegrationCredential | None:
        return self.db.get(IntegrationCredential, provider)

    def save(self, provider: str, refresh_token: str, seed_fingerprint: str) -> None:
        credential = self.get(provider)
        if credential is None:
            credential = IntegrationCredential(provider=provider)
            self.db.add(credential)
        credential.refresh_token = refresh_token
        credential.seed_fingerprint = seed_fingerprint
        # committed on its own, immediately: the token it replaces dies within
        # a minute, so this write must not wait on the rest of the import
        self.db.commit()
