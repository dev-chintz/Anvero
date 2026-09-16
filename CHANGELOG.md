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

#### Order Management
- Order model with UUID primary key
- OrderSource enum: ALLEGRO, ERLI (extensible for future integrations)
- OrderStatus enum: NEW, CONFIRMED, SHIPPED, DELIVERED, CANCELLED
- Monetary amounts stored as Decimal (financial accuracy)
- Order repository with CRUD + filtering (by source, status)
- Order service layer with business logic
- REST endpoints:
  - `GET /orders` (paginated list with source/status filtering)
  - `GET /orders/{order_id}` (fetch single order)
  - `POST /orders` (create order for testing/integration)
- Query parameter filtering: `?source=ALLEGRO`, `?status=NEW`, `?skip=N&limit=M`
- Alembic migration for PostgreSQL orders table

#### Infrastructure
- Initialized Git repository with first commit
- Fixed UTF-16 encoding issue in requirements.txt
- Created virtual environment with all dependencies
- All tests passing (13/13: 6 original + 7 new order tests)

### ✅ Verification

- Rate limiting tested with curl: 5 requests return 401, 6th returns 429
- Order CRUD tests: create, read, filter by source/status, pagination
- Database migration applied cleanly
- All 13 tests passing
- Application startup verified
- slowapi middleware properly wired to FastAPI app

#### Frontend
- React 18 + TypeScript with strict mode
- Vite dev server with HMR
- React Router for navigation
- Custom useOrders hook with pagination/filtering
- Components: OrderList (with filters), OrderRow, OrderDetail, ErrorBoundary
- Pages: Home, OrdersPage (query param sync)
- Mobile-first responsive styling
- API proxy: `/api` → backend `localhost:8000`
- End-to-end verified: frontend fetches real order data from backend

### ✅ Verification

- All 13 backend tests passing
- Frontend TypeScript: 0 errors
- Frontend production build: successful (43 modules)
- Frontend dev server: running (port 5173)
- API proxy: confirmed forwarding requests correctly
- React Router: client-side navigation working
- Order CRUD operations: working end-to-end

### 📌 Sprint 2 Status

**Working skeleton phase COMPLETE:**
- ✅ Backend framework (FastAPI) configured
- ✅ Rate limiting on auth endpoint
- ✅ Order model with REST endpoints
- ✅ Database migrations (users, orders tables)
- ✅ Backend tests: 13/13 passing
- ✅ Frontend skeleton (React + TypeScript)
- ✅ End-to-end integration verified

**Bugs fixed:**
- Migration compatibility: `func.current_timestamp()` for SQLite + PostgreSQL

**Remaining for Sprint 2:**
- Order import from Allegro/ERLI adapters
- Change history tracking

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