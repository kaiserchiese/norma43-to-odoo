"""OdooClient against a real local XML-RPC server (loopback only): proves the wire format."""

import threading
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

import pytest

from builders import join, one_account
from c43_to_odoo import OdooPushError, parse
from c43_to_odoo.push import OdooClient, push

KEY = "test-key-not-real"


class Handler(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/xmlrpc/2/common", "/xmlrpc/2/object")


@pytest.fixture
def server():
    srv = SimpleXMLRPCServer(("127.0.0.1", 0), requestHandler=Handler, logRequests=False)
    created: list = []

    def authenticate(db, user, key, ctx):
        return 5 if (db, user, key) == ("db", "u@example.test", KEY) else False

    def execute_kw(db, uid, key, model, method, args, kwargs):
        assert (db, uid, key) == ("db", 5, KEY)
        if method == "fields_get":
            return {"unique_import_id": {}}
        if model == "account.journal":
            return [{"id": 7, "name": "Bank", "currency_id": [1, "EUR"], "company_id": [1, "Co"]}]
        if method == "search_read":
            return []
        if method == "create":
            created.extend(args[0])
            return [len(created)] * len(args[0])
        raise xmlrpc.client.Fault(1, f"Traceback...\nValueError: no {method}")

    srv.register_function(authenticate)
    srv.register_function(execute_kw)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", created
    srv.shutdown()
    srv.server_close()


def client(url, key=KEY):
    return OdooClient(url, "db", "u@example.test", key)


def test_commit_over_real_xmlrpc_sends_text_amounts(server):
    url, created = server
    report = push(parse(join(*one_account())), client=client(url), commit=True)
    assert len(report.created_ids) == 3
    assert [c["amount"] for c in created] == ["-25.00", "100.00", "-10.00"]
    assert all(c["journal_id"] == 7 for c in created)


def test_bad_credentials_raise_without_leaking_the_key(server):
    url, _ = server
    with pytest.raises(OdooPushError) as exc:
        client(url, key="wrong-key-value").call("x", "y")
    assert "wrong-key-value" not in str(exc.value)


def test_server_fault_becomes_push_error_with_last_line_only(server):
    url, _ = server
    with pytest.raises(OdooPushError, match="ValueError: no boom") as exc:
        client(url).call("res.partner", "boom")
    assert "Traceback" not in str(exc.value)


def test_unreachable_server_is_a_push_error():
    with pytest.raises(OdooPushError, match="could not reach"):
        client("http://127.0.0.1:1").call("x", "y")
