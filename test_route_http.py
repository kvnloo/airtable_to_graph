"""Route-level tests: the real Flask app, with HTTP stubbed at the transport.

Unlike test_relational_columns.py, nothing here extracts functions or mocks
the ``requests`` module. ``main`` is imported as-is and ``GET /`` is driven
through ``app.test_client()``. Every ``requests.Session`` (the one behind
``requests.get`` and the one inside pyairtable) is handed a stub transport
adapter, and a socket guard fails the test if anything tries to reach a
non-loopback address. No real token is used and Airtable is never contacted.
"""

import ipaddress
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import requests
from requests.adapters import BaseAdapter, HTTPAdapter

FAKE_TOKEN = "test-token-not-a-real-key"
FAKE_BASE = "appRouteTest"

sys.path.insert(0, str(Path(__file__).resolve().parent))
# main.py reads the key at import time. Force a fake one for the import so a
# real key in the developer's environment can never be picked up.
with patch.dict(os.environ, {"AIRTABLE_API_KEY": FAKE_TOKEN}):
    import main

# requirements.txt pins Flask 2.3.2 but not Werkzeug, so a fresh install gets
# Werkzeug >= 3.1, which dropped ``werkzeug.__version__``. Flask 2.3.2's test
# client reads it to build a User-Agent; restore it for the tests only.
import werkzeug  # noqa: E402

if not hasattr(werkzeug, "__version__"):
    from importlib.metadata import version

    werkzeug.__version__ = version("werkzeug")

SCHEMA_URL = f"https://api.airtable.com/v0/meta/bases/{FAKE_BASE}/tables"
HANG_LIMIT = 5.0  # seconds before a request is declared hung
SHORT_TIMEOUT = 0.5  # timeout injected for the stalled-fetch test

SCHEMA = {
    "tables": [
        {
            "name": "Companies",
            "fields": [
                {"name": "Name", "type": "singleLineText"},
                {"name": "Tags", "type": "multipleSelects"},
                {"name": "Employees", "type": "multipleRecordLinks"},
            ],
        },
        {
            "name": "People",
            "fields": [{"name": "Name", "type": "singleLineText"}],
        },
    ]
}
COMPANIES = [
    {"id": "recCompany1", "fields": {"Name": "Acme", "Tags": ["b2b"], "Employees": ["recPerson1", "recPerson2"]}},
]
PEOPLE_PAGE_1 = [{"id": "recPerson1", "fields": {"Name": "Ada"}}]
PEOPLE_PAGE_2 = [{"id": "recPerson2", "fields": {"Name": "Grace"}}]


class NonLoopbackConnection(AssertionError):
    """Raised by the socket guard instead of letting a connection leave the host."""


def _is_loopback(host):
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


class SocketGuard:
    """Fail any INET connect or name lookup that is not loopback."""

    def __init__(self):
        self.violations = []
        real_connect = socket.socket.connect
        real_connect_ex = socket.socket.connect_ex
        real_getaddrinfo = socket.getaddrinfo

        def check(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address[0]):
                self.violations.append(address)
                raise NonLoopbackConnection(f"blocked non-loopback connection to {address!r}")

        def connect(sock, address):
            check(sock, address)
            return real_connect(sock, address)

        def connect_ex(sock, address):
            check(sock, address)
            return real_connect_ex(sock, address)

        def getaddrinfo(host, *args, **kwargs):
            if not _is_loopback(host.decode() if isinstance(host, bytes) else host):
                self.violations.append(host)
                raise NonLoopbackConnection(f"blocked name lookup for {host!r}")
            return real_getaddrinfo(host, *args, **kwargs)

        self._patches = [
            patch.object(socket.socket, "connect", connect),
            patch.object(socket.socket, "connect_ex", connect_ex),
            patch.object(socket, "getaddrinfo", getaddrinfo),
        ]

    def start(self):
        for p in self._patches:
            p.start()

    def stop(self):
        for p in self._patches:
            p.stop()


class StubAdapter(BaseAdapter):
    """Transport adapter that answers from a route table instead of the network.

    A route is ``(status, body)`` for a canned reply, a list of those for
    successive calls (pagination), or ``("forward", port)`` to send the request
    for real to a loopback port so genuine socket timeouts are exercised.
    """

    def __init__(self):
        super().__init__()
        self.routes = {}
        self.calls = []
        self._lock = threading.Lock()

    def add(self, url, *replies):
        self.routes[url] = list(replies)

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        parts = urlsplit(request.url)
        url = f"{parts.scheme}://{parts.netloc}{parts.path}"
        with self._lock:
            self.calls.append(
                {
                    "method": request.method,
                    "url": url,
                    "query": parts.query,
                    "timeout": timeout,
                    "authorization": request.headers.get("Authorization"),
                }
            )
            replies = self.routes.get(url)
            if not replies:
                raise AssertionError(f"unexpected HTTP request: {request.method} {request.url}")
            reply = replies.pop(0) if len(replies) > 1 else replies[0]

        if reply[0] == "forward":
            forwarded = request.copy()
            forwarded.url = f"http://127.0.0.1:{reply[1]}{parts.path}"
            return HTTPAdapter().send(forwarded, stream=stream, timeout=timeout, verify=False, proxies={})

        status, body = reply
        response = requests.Response()
        response.status_code = status
        response.reason = {200: "OK", 401: "Unauthorized", 500: "Internal Server Error"}.get(status, "")
        response._content = body if isinstance(body, bytes) else json.dumps(body).encode()
        response.headers["Content-Type"] = "application/json"
        response.encoding = "utf-8"
        response.url = request.url
        response.request = request
        return response

    def close(self):
        pass

    def calls_to(self, url):
        return [call for call in self.calls if call["url"] == url]


def records_url(table_name):
    return f"https://api.airtable.com/v0/{FAKE_BASE}/{table_name}"


class RouteTest(unittest.TestCase):
    def setUp(self):
        self.guard = SocketGuard()
        self.guard.start()
        self.addCleanup(self.guard.stop)

        self.stub = StubAdapter()
        adapter_patch = patch.object(requests.sessions.Session, "get_adapter", lambda session, url: self.stub)
        adapter_patch.start()
        self.addCleanup(adapter_patch.stop)

        for name, value in (("AIRTABLE_API_KEY", FAKE_TOKEN), ("AIRTABLE_BASE_ID", FAKE_BASE)):
            p = patch.object(main, name, value)
            p.start()
            self.addCleanup(p.stop)

        # index() writes static/graph.html relative to the working directory.
        workdir = tempfile.TemporaryDirectory()
        self.addCleanup(workdir.cleanup)
        self.workdir = Path(workdir.name)
        (self.workdir / "static").mkdir()
        previous = os.getcwd()
        os.chdir(self.workdir)
        self.addCleanup(os.chdir, previous)

        main.app.config["TESTING"] = True  # let exceptions reach the test
        self.client = main.app.test_client()

    def tearDown(self):
        self.assertEqual(self.guard.violations, [], "a non-loopback connection was attempted")

    def get_expecting_error(self):
        """GET / and return the exception the route raised."""
        with self.assertRaises(Exception) as caught:
            self.client.get("/")
        return caught.exception

    def assert_schema_error(self, exc, *fragments):
        self.assertEqual(type(exc).__name__, "AirtableSchemaError", f"got {exc!r}")
        self.assertIsInstance(exc, main.AirtableSchemaError)
        for fragment in fragments:
            self.assertIn(fragment, str(exc))

    def add_happy_records(self):
        self.stub.add(records_url("Companies"), (200, {"records": COMPANIES}))
        self.stub.add(
            records_url("People"),
            (200, {"records": PEOPLE_PAGE_1, "offset": "page2"}),
            (200, {"records": PEOPLE_PAGE_2}),
        )

    # -- guard ------------------------------------------------------------

    def test_socket_guard_blocks_non_loopback_connections(self):
        with self.assertRaises(NonLoopbackConnection):
            socket.create_connection(("192.0.2.1", 9), timeout=1)  # TEST-NET-1, never dialled
        with self.assertRaises(NonLoopbackConnection):
            socket.getaddrinfo("api.airtable.com", 443)
        self.assertEqual(len(self.guard.violations), 2)
        self.guard.violations.clear()

    # -- happy path -------------------------------------------------------

    def test_happy_path_renders_graph_and_bounds_every_request(self):
        self.stub.add(SCHEMA_URL, (200, SCHEMA))
        self.add_happy_records()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"static/graph.html", response.data)
        graph = (self.workdir / "static" / "graph.html").read_text()
        for node_id in ("recCompany1", "recPerson1", "recPerson2"):
            self.assertIn(node_id, graph)
        self.assertIn("Employees", graph)  # edge title from the linked-record field
        self.assertNotIn("b2b", graph)  # a multi-select value is not a node

        self.assertEqual(len(self.stub.calls_to(SCHEMA_URL)), 1)
        self.assertEqual(len(self.stub.calls_to(records_url("Companies"))), 1)
        people_calls = self.stub.calls_to(records_url("People"))
        self.assertEqual(len(people_calls), 2)
        self.assertIn("offset=page2", people_calls[1]["query"])
        for call in self.stub.calls:
            self.assertEqual(call["method"], "GET")
            self.assertEqual(call["authorization"], f"Bearer {FAKE_TOKEN}")
            self.assertEqual(call["timeout"], 30, f"no 30 s timeout on {call['url']}")

    # -- schema HTTP errors -----------------------------------------------

    def test_schema_http_errors_name_the_status(self):
        cases = {
            401: b'{"error": {"type": "AUTHENTICATION_REQUIRED"}}',
            500: b"<html><body>Internal Server Error</body></html>",
        }
        for status, body in cases.items():
            with self.subTest(status=status):
                self.stub.calls.clear()
                self.stub.add(SCHEMA_URL, (status, body))

                exc = self.get_expecting_error()

                self.assertIsInstance(exc, requests.exceptions.HTTPError, f"got {exc!r}")
                self.assertEqual(exc.response.status_code, status)
                self.assertIn(str(status), str(exc))
                # Nothing else is fetched once the schema request has failed.
                self.assertEqual([call["url"] for call in self.stub.calls], [SCHEMA_URL])

    # -- schema payload shape ---------------------------------------------

    def test_schema_200_with_malformed_json_is_a_clear_error(self):
        self.stub.add(SCHEMA_URL, (200, b"<html>gateway says hi</html>"))

        exc = self.get_expecting_error()

        self.assert_schema_error(exc, "not valid JSON")
        self.assertEqual([call["url"] for call in self.stub.calls], [SCHEMA_URL])

    def test_schema_200_without_tables_is_a_clear_error(self):
        payloads = {
            "no tables key": {"unexpected": True},
            "tables is null": {"tables": None},
            "tables is an object": {"tables": {"name": "Companies"}},
            "payload is a list": [],
        }
        for label, payload in payloads.items():
            with self.subTest(label):
                self.stub.calls.clear()
                self.stub.add(SCHEMA_URL, (200, payload))

                exc = self.get_expecting_error()

                self.assert_schema_error(exc, '"tables"')
                self.assertEqual([call["url"] for call in self.stub.calls], [SCHEMA_URL])

    # -- stalled records fetch --------------------------------------------

    def test_stalled_records_fetch_times_out_instead_of_hanging(self):
        # A loopback listener that completes the TCP handshake (kernel
        # backlog) and never sends a byte back.
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        self.addCleanup(listener.close)

        self.stub.add(SCHEMA_URL, (200, SCHEMA))
        self.stub.add(records_url("Companies"), ("forward", listener.getsockname()[1]))
        self.stub.add(records_url("People"), (200, {"records": PEOPLE_PAGE_1}))

        outcome = {}

        def drive():
            try:
                outcome["response"] = self.client.get("/")
            except BaseException as exc:  # noqa: BLE001 - reported below
                outcome["error"] = exc

        with patch.object(main, "AIRTABLE_TIMEOUT", SHORT_TIMEOUT, create=True):
            worker = threading.Thread(target=drive, daemon=True)
            started = time.monotonic()
            worker.start()
            worker.join(HANG_LIMIT)
            elapsed = time.monotonic() - started
            hung = worker.is_alive()
            if hung:
                # Release the stalled request so the test run can finish.
                listener.close()
                worker.join(HANG_LIMIT)

        stalled = self.stub.calls_to(records_url("Companies"))
        self.assertEqual(len(stalled), 1)
        self.assertFalse(
            hung,
            f"records fetch still blocked after {HANG_LIMIT} s "
            f"(timeout passed to the transport: {stalled[0]['timeout']!r})",
        )
        self.assertEqual(stalled[0]["timeout"], SHORT_TIMEOUT)
        self.assertIsInstance(outcome.get("error"), requests.exceptions.Timeout, f"got {outcome!r}")
        self.assertLess(elapsed, HANG_LIMIT)


if __name__ == "__main__":
    unittest.main()
