from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
class TestHealthCheck:
    """Test suite for system health check endpoint."""

    def test_health_check_success(self, client: Client):
        """Health check returns 200 and healthy status when database is reachable."""
        url = reverse("core:health_check")
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["components"]["database"] == "healthy"

    def test_health_check_database_failure(self, client: Client):
        """Health check returns 503 and unhealthy status when database connection fails."""
        url = reverse("core:health_check")
        with patch("django.db.connection.cursor", side_effect=DatabaseError("Connection lost")):
            response = client.get(url)

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "unhealthy" in data["components"]["database"]

    def test_index_page_loads(self, client: Client):
        """Landing page renders successfully."""
        url = reverse("core:index")
        response = client.get(url)

        assert response.status_code == 200
        assert b"mycatalogue System Foundation" in response.content
        assert b"hx-headers" in response.content
