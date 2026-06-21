---
name: python-testing-patterns
description: Implement comprehensive testing strategies with pytest, fixtures, mocking, and test-driven development. Use when writing Python tests, setting up test suites, or implementing testing best practices.
---

# Python Testing Patterns

## Fixtures

```python
import pytest
from typing import Generator

@pytest.fixture
def db() -> Generator[Database, None, None]:
    database = Database("sqlite:///:memory:")
    database.connect()
    yield database
    database.disconnect()

@pytest.fixture(scope="session")
def app_config():
    return {"database_url": "postgresql://localhost/test", "api_key": "test-key", "debug": True}

@pytest.fixture(scope="module")
def api_client(app_config):
    client = {"config": app_config, "session": "active"}
    yield client
    client["session"] = "closed"

def test_database_query(db):
    results = db.query("SELECT * FROM users")
    assert len(results) == 1
```

## Parameterized Tests

```python
@pytest.mark.parametrize("email,expected", [
    ("user@example.com", True),
    ("invalid.email", False),
    ("@example.com", False),
])
def test_email_validation(email, expected):
    assert is_valid_email(email) == expected

# Custom test IDs
@pytest.mark.parametrize("value,expected", [
    pytest.param(1, True, id="positive"),
    pytest.param(0, False, id="zero"),
])
def test_is_positive(value, expected):
    assert (value > 0) == expected
```

## Mocking with unittest.mock

```python
from unittest.mock import Mock, patch, MagicMock

# Context manager style
def test_get_user_success():
    client = APIClient("https://api.example.com")
    mock_response = Mock()
    mock_response.json.return_value = {"id": 1, "name": "John Doe"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response) as mock_get:
        user = client.get_user(1)
        assert user["id"] == 1
        mock_get.assert_called_once_with("https://api.example.com/users/1")

# Decorator style
@patch("requests.post")
def test_create_user(mock_post):
    client = APIClient("https://api.example.com")
    mock_post.return_value.json.return_value = {"id": 2}
    mock_post.return_value.raise_for_status.return_value = None

    result = client.create_user({"name": "Jane"})
    assert result["id"] == 2
    mock_post.assert_called_once()

# Exception mocking
def test_get_user_not_found():
    client = APIClient("https://api.example.com")
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("404")

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(requests.HTTPError):
            client.get_user(999)
```

## Retry Pattern Testing

```python
def test_retries_on_transient_error():
    client = Mock()
    client.request.side_effect = [
        ConnectionError("Failed"),
        ConnectionError("Failed"),
        {"status": "ok"},
    ]
    service = ServiceWithRetry(client, max_retries=3)
    result = service.fetch()
    assert result == {"status": "ok"}
    assert client.request.call_count == 3

def test_gives_up_after_max_retries():
    client = Mock()
    client.request.side_effect = ConnectionError("Failed")
    service = ServiceWithRetry(client, max_retries=3)
    with pytest.raises(ConnectionError):
        service.fetch()
    assert client.request.call_count == 3

def test_does_not_retry_on_permanent_error():
    client = Mock()
    client.request.side_effect = ValueError("Invalid input")
    service = ServiceWithRetry(client, max_retries=3)
    with pytest.raises(ValueError):
        service.fetch()
    assert client.request.call_count == 1
```

## Mocking Time with Freezegun

```python
from freezegun import freeze_time
from datetime import datetime

@freeze_time("2026-01-15 10:00:00")
def test_token_expiry():
    token = create_token(expires_in_seconds=3600)
    assert token.expires_at == datetime(2026, 1, 15, 11, 0, 0)

def test_with_time_travel():
    with freeze_time("2026-01-01") as frozen_time:
        item = create_item()
        assert item.created_at == datetime(2026, 1, 1)
        frozen_time.move_to("2026-01-15")
        assert item.age_days == 14
```

For async testing, monkeypatching, property-based testing, database testing, and conftest setup, see [references/advanced-patterns.md](references/advanced-patterns.md)
