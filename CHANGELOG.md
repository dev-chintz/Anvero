# Changelog

Wszystkie istotne zmiany w projekcie Anvero.

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