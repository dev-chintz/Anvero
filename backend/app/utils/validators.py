import re
from typing import Optional


class PasswordValidator:
    """Validate password strength according to security requirements."""

    MIN_LENGTH = 8
    SPECIAL_CHARS = r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]"

    @staticmethod
    def validate(password: str) -> Optional[str]:
        """Validate password. Returns error message or None if valid."""
        if len(password) < PasswordValidator.MIN_LENGTH:
            return f"Password must be at least {PasswordValidator.MIN_LENGTH} characters long"

        if not re.search(r"[A-Z]", password):
            return "Password must contain at least one uppercase letter"

        if not re.search(r"\d", password):
            return "Password must contain at least one digit"

        if not re.search(PasswordValidator.SPECIAL_CHARS, password):
            return "Password must contain at least one special character"

        return None
