from sqlalchemy.orm import Session

from app.models.integration import IntegrationSettings


class IntegrationSettingsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, provider: str) -> IntegrationSettings | None:
        return self.db.get(IntegrationSettings, provider)

    def save(
        self,
        provider: str,
        client_id: str,
        client_secret: str,
        user_agent: str,
        environment: str,
    ) -> IntegrationSettings:
        settings = self.get(provider)
        if settings is None:
            settings = IntegrationSettings(provider=provider)
            self.db.add(settings)
        settings.client_id = client_id
        settings.client_secret = client_secret
        settings.user_agent = user_agent
        settings.environment = environment
        self.db.commit()
        self.db.refresh(settings)
        return settings
