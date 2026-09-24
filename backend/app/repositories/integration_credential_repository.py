from datetime import UTC, datetime

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

    def last_billing_synced_at(self, provider: str) -> datetime | None:
        credential = self.get(provider)
        return credential.last_billing_synced_at if credential else None

    def set_last_billing_synced_at(self, provider: str, value: datetime) -> bool:
        credential = self.get(provider)
        if credential is None:
            return False
        credential.last_billing_synced_at = value
        self.db.commit()
        return True

    def record_import(
        self,
        provider: str,
        finished_at: datetime,
        created: int = 0,
        updated: int = 0,
        error: str | None = None,
    ) -> bool:
        """Note how an import ended; False if there is no row to note it on."""
        credential = self.get(provider)
        if credential is None:
            return False
        credential.last_import_at = finished_at
        credential.last_import_created = None if error else created
        credential.last_import_updated = None if error else updated
        credential.last_import_error = error
        self.db.commit()
        return True

    def connect(
        self,
        provider: str,
        refresh_token: str,
        seed_fingerprint: str,
        account_login: str | None,
    ) -> None:
        """Store the token of a freshly connected account, replacing any other.

        Unlike `save`, which follows a rotation of the same chain, this always
        forgets where the last sync got to: the account just connected may be
        another seller's, or the same one reconnected, and either way starting
        from the first-import window is the safe choice.
        """
        credential = self.get(provider)
        if credential is None:
            credential = IntegrationCredential(provider=provider)
            self.db.add(credential)
        credential.refresh_token = refresh_token
        credential.token_issued_at = datetime.now(UTC)
        credential.seed_fingerprint = seed_fingerprint
        credential.account_login = account_login
        credential.last_synced_at = None
        credential.last_billing_synced_at = None
        credential.last_import_at = None
        credential.last_import_created = None
        credential.last_import_updated = None
        credential.last_import_error = None
        self.db.commit()

    def set_account_login(self, provider: str, login: str | None) -> None:
        credential = self.get(provider)
        if credential is not None:
            credential.account_login = login
            self.db.commit()

    def disconnect(self, provider: str) -> bool:
        credential = self.get(provider)
        if credential is None:
            return False
        self.db.delete(credential)
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
            credential.last_billing_synced_at = None
        if refresh_token and refresh_token != credential.refresh_token:
            # a rotation: the token just issued lives from now
            credential.token_issued_at = datetime.now(UTC)
        credential.refresh_token = refresh_token
        credential.seed_fingerprint = seed_fingerprint
        # committed on its own, immediately: the token it replaces dies within
        # a minute, so this write must not wait on the rest of the import
        self.db.commit()
