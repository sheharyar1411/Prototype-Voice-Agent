"""
Shared test fixtures for the Patient Registration System test suite.

Provides:
  - In-memory SQLite async engine and session for isolated DB tests
  - FastAPI TestClient with dependency overrides
  - Sample patient data factories for consistent test inputs
"""

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import get_db
from app.main import app
from app.models.patient import Base


# ---------------------------------------------------------------------------
# Async event loop fixture (session-scoped for test efficiency)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# In-memory SQLite database for test isolation
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an isolated async database session backed by in-memory SQLite.

    Each test gets a fresh database with all tables created, ensuring
    complete isolation between tests.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ---------------------------------------------------------------------------
# FastAPI test client with DB dependency override
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an httpx AsyncClient wired to the FastAPI app with a test DB.

    Overrides the get_db dependency to use the in-memory SQLite session,
    ensuring API tests don't touch real databases.
    """

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample data factories
# ---------------------------------------------------------------------------

def valid_patient_data(**overrides) -> dict:
    """
    Return a complete, valid patient registration payload.

    Accepts keyword overrides to customize specific fields for
    targeted test scenarios.
    """
    data = {
        "first_name": "John",
        "last_name": "Smith",
        "date_of_birth": "1990-05-15",
        "sex": "Male",
        "phone_number": "5125550199",
        "address_line_1": "123 Main Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
    }
    data.update(overrides)
    return data


def valid_patient_data_with_optionals(**overrides) -> dict:
    """
    Return a patient payload with all optional fields populated.
    """
    data = valid_patient_data()
    data.update({
        "email": "john.smith@example.com",
        "address_line_2": "Apt 4B",
        "insurance_provider": "Blue Cross Blue Shield",
        "insurance_member_id": "BCB-12345678",
        "preferred_language": "English",
        "emergency_contact_name": "Jane Smith",
        "emergency_contact_phone": "5125550200",
    })
    data.update(overrides)
    return data
