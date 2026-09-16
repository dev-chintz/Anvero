import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger("security")


class SecurityEvent(str, Enum):
    """Security event types."""

    REGISTER_ATTEMPT = "REGISTER_ATTEMPT"
    REGISTER_SUCCESS = "REGISTER_SUCCESS"
    REGISTER_FAILED = "REGISTER_FAILED"
    LOGIN_ATTEMPT = "LOGIN_ATTEMPT"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    RATE_LIMIT_HIT = "RATE_LIMIT_HIT"
    INVALID_PASSWORD = "INVALID_PASSWORD"
    USER_NOT_FOUND = "USER_NOT_FOUND"


class SecurityLogger:
    """Log security events with structured context."""

    @staticmethod
    def log(
        event: SecurityEvent,
        email: Optional[str] = None,
        details: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Log a security event."""
        message = f"[{event.value}]"
        if email:
            message += f" email={email}"
        if details:
            message += f" {details}"
        if user_agent:
            message += f" user_agent={user_agent[:50]}"

        logger.warning(message)

    @staticmethod
    def register_attempt(email: str) -> None:
        SecurityLogger.log(SecurityEvent.REGISTER_ATTEMPT, email=email)

    @staticmethod
    def register_success(email: str) -> None:
        SecurityLogger.log(SecurityEvent.REGISTER_SUCCESS, email=email)

    @staticmethod
    def register_failed(email: str, reason: str) -> None:
        SecurityLogger.log(SecurityEvent.REGISTER_FAILED, email=email, details=reason)

    @staticmethod
    def login_attempt(email: str) -> None:
        SecurityLogger.log(SecurityEvent.LOGIN_ATTEMPT, email=email)

    @staticmethod
    def login_success(email: str) -> None:
        SecurityLogger.log(SecurityEvent.LOGIN_SUCCESS, email=email)

    @staticmethod
    def login_failed(email: str, reason: str) -> None:
        SecurityLogger.log(SecurityEvent.LOGIN_FAILED, email=email, details=reason)

    @staticmethod
    def rate_limit_hit(email: str, attempts: int) -> None:
        SecurityLogger.log(
            SecurityEvent.RATE_LIMIT_HIT,
            email=email,
            details=f"attempts={attempts}",
        )

    @staticmethod
    def invalid_password(email: str) -> None:
        SecurityLogger.log(SecurityEvent.INVALID_PASSWORD, email=email)

    @staticmethod
    def user_not_found(email: str) -> None:
        SecurityLogger.log(SecurityEvent.USER_NOT_FOUND, email=email)
