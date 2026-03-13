from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.dependencies import get_current_user_id, require_role


@pytest.mark.asyncio
async def test_require_role_success():
    """Test that require_role allows access when the user has the correct role."""
    mock_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_token")
    mock_user = MagicMock()
    mock_user.id = "user123"
    mock_user.email = "test@example.com"
    mock_user.user_metadata = {"role": "admin"}

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.user = mock_user
    mock_client.auth.get_user.return_value = mock_response

    # A coroutine that returns the mock client
    async def mock_proxy():
        return mock_client

    with patch("app.dependencies.db", mock_proxy()):
        checker = require_role("admin")
        result = await checker(mock_creds)

        assert result["id"] == "user123"
        assert result["role"] == "admin"


@pytest.mark.asyncio
async def test_require_role_forbidden():
    """Test that require_role blocks access when the user has the wrong role."""
    mock_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_token")
    mock_user = MagicMock()
    mock_user.user_metadata = {"role": "victim"}

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.user = mock_user
    mock_client.auth.get_user.return_value = mock_response

    async def mock_proxy():
        return mock_client

    with patch("app.dependencies.db", mock_proxy()):
        checker = require_role("admin")
        with pytest.raises(HTTPException) as exc:
            await checker(mock_creds)

        assert exc.value.status_code == 403
        assert "Required role: admin" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_id_success():
    mock_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_token")
    mock_user = MagicMock()
    mock_user.id = "user123"

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.user = mock_user
    mock_client.auth.get_user.return_value = mock_response

    async def mock_proxy():
        return mock_client

    with patch("app.dependencies.db", mock_proxy()):
        result = await get_current_user_id(mock_creds)
        assert result == "user123"
