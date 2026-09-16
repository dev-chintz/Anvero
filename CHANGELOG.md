# Changelog

All significant changes to the Anvero project.

---

## 2026-09-16

### ✨ Added

#### Security
- Implemented rate limiting on `/api/v1/auth/login` endpoint
- Rate limit: 5 attempts per minute per IP address
- Configurable rate limit via `RATE_LIMIT_LOGIN` setting
- Returns 429 Too Many Requests when limit exceeded

#### Infrastructure
- Initialized Git repository with first commit
- Fixed UTF-16 encoding issue in requirements.txt
- Created virtual environment with all dependencies
- Verified all 6 existing tests pass

### ✅ Verification

- Rate limiting tested with curl: 5 requests return 401, 6th returns 429
- All tests passing (6/6)
- Application startup verified
- slowapi middleware properly wired to FastAPI app

### 📌 Sprint 2 Status

Foundation complete. Ready for:
- Order model implementation
- Order list endpoint
- Frontend skeleton

---

## 2026-08-06

### ✨ Added

#### Authentication
- Added JWT authentication.
- Implemented `AuthService`.
- Added `/api/v1/auth/login` endpoint.
- Implemented password verification.
- Implemented JWT access token generation.
- Added OAuth2 support for FastAPI.

#### Users
- Added persistent user registration.
- Added duplicate email validation.
- User passwords are now stored as hashed values.
- Registration now persists users in PostgreSQL.

#### Database
- Configured Alembic.
- Created initial migration for the `users` table.
- Alembic now uses FastAPI application settings.
- Added automatic model discovery for migrations.

#### API
- Added authentication router.
- Updated users endpoint to use dependency injection.
- Added proper response models.

#### Tests
- Added registration API tests.
- Added duplicate registration test.
- Registration tests now generate unique email addresses.

### 🔧 Changed

- Configuration now loads `.env` correctly regardless of the current working directory.
- SQLAlchemy session configuration cleaned up.
- Repository and service layers fully integrated.
- Project architecture aligned around:
  - Repository
  - Service
  - API Endpoint

### 🧠 Architecture

Implemented layered architecture:

```text
API
 │
 ▼
Service
 │
 ▼
Repository
 │
 ▼
Database
```

JWT flow:

```text
Login
 │
 ▼
AuthService
 │
 ▼
UserRepository
 │
 ▼
verify_password()
 │
 ▼
create_access_token()
 │
 ▼
JWT
```

### ✅ Verification

- Alembic migrations working.
- User registration verified.
- Login verified.
- JWT generation verified.
- Swagger integration verified.
- All tests passing.

### 📌 Next Sprint

- Implement `get_current_user()`
- Add `GET /users/me`
- Enable Swagger Authorize
- Add authentication tests
- Protect authenticated endpoints