from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse


class HealthViewTests(TestCase):
    def test_health_checks_the_database(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    @patch(
        "config.views._check_database",
        side_effect=OperationalError("base indisponible"),
    )
    def test_health_returns_503_when_the_database_is_unavailable(self, _check):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(), {"status": "error", "database": "unavailable"}
        )
