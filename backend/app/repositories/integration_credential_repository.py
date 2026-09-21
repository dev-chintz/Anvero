from datetime import datetime

from sqlalchemy.orm import Session

from app.models.integration import IntegrationCredential


class IntegrationCredentialRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, provider: str) -> IntegrationCredential | None:
        return self.db.get(IntegrationCredential, provider)

    def last_synced_at(self, provider: str) -> datetime | None:
        credential = self.get(provider)
        return credential.last_synced_at if credential else None

    def set_last_synced_at(self, provider: str, value: datetime) -> bool:
        """Record where the next import resumes; False if there is no row.

        The row is created by the first token rotation, which every import
        performs before fetching anything, so a missing one means the import
        did not really run.
        """
        credential = self.get(provider)
        if credential is None:
            return False
        credential.last_synced_at = value
        self.db.commit()
        return True

    def save(self, provider: str, refresh_token: str, seed_fingerprint: str) -> None:
        credential = self.get(provider)
        if credential is None:
            credential = IntegrationCredential(provider=provider)
            self.db.add(credential)
        elif credential.seed_fingerprint != seed_fingerprint:
            # authorized again, possibly as another seller: what was fetched
            # for the previous account says nothing about this one
            credential.last_synced_at = None
        credential.refresh_token = refresh_token
        credential.seed_fingerprint = seed_fingerprint
        # committed on its own, immediately: the token it replaces dies within
        # a minute, so this write must not wait on the rest of the import
        self.db.commit()
