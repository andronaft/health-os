"""When Postgres isn't answering (e.g. Docker Desktop stopped): the crisis response still comes
back in full, and every other tool says what's wrong instead of a bare "Error executing tool"."""
import json

import pytest
from sqlalchemy.exc import OperationalError

from mcp_server import server, tools, write_tools


class _Down:
    def connect(self):
        raise OperationalError("SELECT 1", {}, Exception("connection refused\nmore detail"))

    begin = connect


@pytest.fixture()
def db_down(monkeypatch):
    for mod, name in ((tools, "engine"), (tools, "rw_engine"), (write_tools, "engine")):
        monkeypatch.setattr(mod, name, _Down())


def test_crisis_response_does_not_depend_on_the_database(db_down):
    out = json.loads(server.crisis_resources("test"))
    assert out["response"] and "instruction" in out


@pytest.mark.parametrize("call", [
    lambda: server.get_medications(),
    lambda: server.query_observations("ldl"),
    lambda: server.get_anomalies(),
    lambda: server.log_meal("rice"),
])
def test_tools_explain_an_unreachable_database(db_down, call):
    out = json.loads(call())
    assert out["error"] == "database unreachable"
    assert "Docker" in out["hint"] and out["detail"] == "connection refused"
