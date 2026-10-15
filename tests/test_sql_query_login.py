"""sql_query runs model-written SQL only on the restricted read-only login."""
import json

import pytest
from sqlalchemy import text

from mcp_server import tools

pytestmark = pytest.mark.integration


def test_sql_query_refuses_a_login_that_is_more_than_read_only():
    # the test DB login is a superuser, like the default Docker setup without READONLY_DATABASE_URL
    out = json.loads(tools.sql_query("SELECT 1"))
    assert "READONLY_DATABASE_URL" in out["error"] and "rows" not in out


def test_login_check(conn):
    assert tools._login_can_leave_readonly(conn) is True          # superuser / table owner
    conn.execute(text("SET LOCAL SESSION AUTHORIZATION health_readonly"))
    assert tools._login_can_leave_readonly(conn) is False         # the view-only login
