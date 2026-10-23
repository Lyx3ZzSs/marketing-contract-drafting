"""Business unit tests use an explicit identity; auth tests exercise the real boundary."""

from collections.abc import Iterator

import pytest

from app.auth import Principal, current_principal, require_access
from app.main import app


@pytest.fixture(autouse=True)
def business_test_identity(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.get_closest_marker("auth"):
        yield
        return
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[require_access] = lambda: None
    app.dependency_overrides[current_principal] = lambda: Principal(
        sub="unit-test-admin", roles=frozenset({"agent_admin"}), expires_at=4102444800
    )
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
