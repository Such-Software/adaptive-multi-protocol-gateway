from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest

from ampg.dns import ProviderDNSRecord
from ampg.dynadot_dns import DynadotDNSProvider, dynadot_signature


class FakeResponse:
    def __init__(self, document):
        self.document = document

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        return False

    def read(self):
        return json.dumps(self.document).encode("utf-8")


class DynadotDNSTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.credentials = Path(self.temporary.name) / "dynadot.ini"
        self.credentials.write_text(
            "api_base_url=https://api-sandbox.dynadot.com\n"
            "api_key=test-key\n"
            "api_secret=test-secret\n"
            "allowed_source_cidr=192.0.2.10/32\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_signature_matches_documented_hmac_shape(self):
        message = "test-key\n/restful/v2/domains/example.test/records\nrequest-id\n"
        expected = base64.b64encode(
            hmac.new(
                b"test-secret", message.encode(), hashlib.sha256
            ).digest()
        ).decode()
        self.assertEqual(
            expected,
            dynadot_signature(
                "test-key",
                "test-secret",
                "/restful/v2/domains/example.test/records",
                "request-id",
            ),
        )

    def test_fetch_preserves_all_provider_fields_and_secrets_stay_out_of_url(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "glue_info": {
                            "glue_type": "DNS",
                            "ttl": 1800,
                            "dns_main_list": [
                                {
                                    "record_type": "MX",
                                    "value1": "mail.example.test.",
                                    "value2": "10",
                                }
                            ],
                            "dns_sub_list": [
                                {
                                    "sub_host": "old",
                                    "record_type": "FORWARD",
                                    "value1": "https://example.test/",
                                    "value2": "301",
                                }
                            ],
                        }
                    },
                }
            )

        provider = DynadotDNSProvider(
            credentials=self.credentials,
            opener=opener,
            request_id_factory=lambda: "550e8400-e29b-41d4-a716-446655440000",
        )
        snapshot = provider.get_hosts("example.test")
        self.assertEqual(1800, snapshot.zone_ttl)
        self.assertEqual(10, snapshot.records[0].mx_pref)
        self.assertEqual("301", snapshot.records[1].provider_value2)
        self.assertNotIn("test-key", requests[0].full_url)
        self.assertNotIn("test-secret", requests[0].full_url)
        self.assertEqual("Bearer test-key", requests[0].headers["Authorization"])

    def test_full_zone_write_is_canonical_and_lossless(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse({"code": 200, "data": {}})

        provider = DynadotDNSProvider(
            credentials=self.credentials,
            opener=opener,
            request_id_factory=lambda: "550e8400-e29b-41d4-a716-446655440000",
        )
        provider.set_hosts(
            "example.test",
            (
                ProviderDNSRecord(
                    "@", "MX", "mail.example.test.", 1800, 10
                ),
                ProviderDNSRecord(
                    "old",
                    "FORWARD",
                    "https://example.test/",
                    1800,
                    provider_value2="301",
                ),
            ),
            mail_policy="preserve",
        )
        body = json.loads(requests[0].data)
        self.assertFalse(body["add_dns_to_current_setting"])
        # record_value1/record_value2, the spelling Dynadot uses in both
        # directions. This test asserted value2 and passed while every write was
        # refused with "if record_type is entered, record_value1 must be
        # entered", because it encoded the same wrong assumption as the code.
        for entry in body["dns_main_list"] + body["dns_sub_list"]:
            self.assertIn("record_value1", entry)
            self.assertNotIn("value1", entry)
            self.assertNotIn("value2", entry)
        self.assertEqual("10", body["dns_main_list"][0]["record_value2"])
        self.assertEqual("301", body["dns_sub_list"][0]["record_value2"])

    def test_a_zone_survives_being_read_and_written_back(self):
        """Read a zone, write it back unchanged, and lose nothing.

        The read and write paths disagreed about field names twice in a row, in
        opposite directions, and each time the unit tests passed because they
        encoded the same assumption as the code they tested. A round trip cannot:
        it feeds the writer exactly what the reader produced, so a spelling the
        two do not share shows up as a value that vanished.

        This matters because set_hosts replaces the whole zone. A record the
        reader drops or the writer misnames is a record deleted from a live
        domain, and suchshop.lol is a shop.
        """
        live = {
            "code": 200,
            "data": {"glue_info": {
                "glue_type": "DNS",
                "ttl": "300",
                "dns_main_list": [
                    {"record_type": "txt", "record_value1": "v=spf1 mx -all"},
                    {"record_type": "a", "record_value1": "203.0.113.10"},
                ],
                "dns_sub_list": [
                    {"record_type": "mx", "record_value1": "mail.example.test",
                     "record_value2": "10", "sub_host": "mail"},
                    {"record_type": "txt", "record_value1": "v=DKIM1;k=rsa;p=AAAA",
                     "sub_host": "modoboa._domainkey"},
                ],
            }},
        }
        written = []

        def opener(request, timeout=None):
            if request.get_method() == "POST":
                written.append(json.loads(request.data))
                return FakeResponse({"code": 200, "data": {}})
            return FakeResponse(live)

        provider = DynadotDNSProvider(credentials=self.credentials, opener=opener)
        snapshot = provider.get_hosts("example.test")
        provider.set_hosts("example.test", tuple(snapshot.records), mail_policy="preserve")

        body = written[0]
        self.assertEqual(300, body["ttl"], "the string TTL must come back as a number")

        def flatten(main, sub):
            out = set()
            for entry in main:
                out.add(("@", entry["record_type"], entry["record_value1"]))
            for entry in sub:
                out.add((entry["sub_host"], entry["record_type"], entry["record_value1"]))
            return out

        before = flatten(
            live["data"]["glue_info"]["dns_main_list"],
            live["data"]["glue_info"]["dns_sub_list"],
        )
        after = flatten(body["dns_main_list"], body["dns_sub_list"])
        # Types are upper-cased on the way out, which is Dynadot's own form.
        before = {(n, t.upper(), v) for n, t, v in before}
        self.assertEqual(before, after, "a record changed or vanished in the round trip")

        # The MX preference is carried in the second value and is easy to drop.
        mx = [e for e in body["dns_sub_list"] if e["record_type"] == "MX"][0]
        self.assertEqual("10", mx["record_value2"])

    def test_a_dropped_connection_is_retried(self):
        # Dynadot drops connections: three plain requests gave 000, 200, 000
        # within seconds, and a full-zone write died mid-TLS.
        import ssl as ssl_module

        attempts = {"n": 0}

        def opener(request, timeout=None):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ssl_module.SSLError("UNEXPECTED_EOF_WHILE_READING")
            return FakeResponse({"code": 200, "data": {"glue_info": {
                "glue_type": "DNS", "ttl": "300",
                "dns_main_list": [{"record_type": "txt", "record_value1": "v=spf1 -all"}],
                "dns_sub_list": [],
            }}})

        # The injected opener replaces the retrying sender, so this asserts the
        # policy rather than the transport: a caller that retries is what the
        # real sender now is.
        from ampg import dynadot_dns
        self.assertEqual(3, dynadot_dns._CONNECTION_ATTEMPTS)
        self.assertEqual(2, len(dynadot_dns._RETRY_BACKOFF_SECONDS))

    def test_an_http_status_is_never_retried(self):
        """A status is an answer, and repeating it turns one refusal into three.

        urllib.error.HTTPError subclasses OSError, which the retry does catch,
        so this is only correct because the status is raised after the loop has
        already succeeded. Asserted structurally: moving that raise inside the
        try would silently start retrying every 400, and no unit test that
        stubs the opener would notice, because the stub replaces the retry.
        """
        source = (Path(__file__).resolve().parents[1] / "ampg/dynadot_dns.py").read_text()
        loop = source.index("for attempt in range(_CONNECTION_ATTEMPTS)")
        status_check = source.index("if status >= 400:", loop)
        raise_status = source.index("raise urllib.error.HTTPError(", status_check)
        self.assertGreater(raise_status, status_check)
        # The retry clause catches transport failures only, by name.
        clause = source[source.index("except (", loop):source.index("as error:", loop)]
        self.assertNotIn("HTTPError", clause)
        for expected in ("SSLError", "ConnectionError", "TimeoutError"):
            self.assertIn(expected, clause)

    def test_retrying_a_write_is_only_safe_because_it_replaces_the_zone(self):
        # If the write ever appends instead, this reasoning stops holding.
        source = (Path(__file__).resolve().parents[1] / "ampg/dynadot_dns.py").read_text()
        self.assertIn('"add_dns_to_current_setting": False', source)
        self.assertIn("does not transfer to an endpoint that appends", source)

    def test_http_error_body_reaches_the_operator(self):
        """A status code with no explanation is not a diagnosis.

        Dynadot says why in the body. For a 400 that is the difference between
        the domain not being in this account and the signature being wrong, and
        the operator was handed neither.
        """
        import io
        import urllib.error

        def opener(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {},
                io.BytesIO(b'{"error":"domain not found in this account"}'),
            )

        provider = DynadotDNSProvider(credentials=self.credentials, opener=opener)
        with self.assertRaises(RuntimeError) as caught:
            provider.get_hosts("example.test")
        message = str(caught.exception)
        self.assertIn("HTTP 400", message)
        self.assertIn("domain not found in this account", message)

    def test_an_unreadable_body_does_not_cost_the_status_code(self):
        # The body is a bonus. Losing it must not lose the code as well.
        import urllib.error

        def opener(request, timeout=None):
            error = urllib.error.HTTPError(request.full_url, 503, "x", {}, None)

            def explode():
                raise OSError("stream gone")

            error.read = explode
            raise error

        provider = DynadotDNSProvider(credentials=self.credentials, opener=opener)
        with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
            provider.get_hosts("example.test")

    def test_request_id_header_keeps_its_exact_case_on_the_wire(self):
        """Dynadot matches X-Request-ID exactly, against RFC 9110.

        urllib capitalises header names when they go through add_header, so
        X-Request-ID left as X-request-id. Dynadot did not find it, signed with
        an empty request id while we signed with the UUID, and rejected the
        result as an invalid signature. Every request this provider made failed,
        and the message pointed at the algorithm and the credentials.
        """
        seen = {}

        def opener(request, timeout=None):
            seen.update(dict(request.header_items()))
            return FakeResponse({"code": 200, "data": {"glue_info": {"glue_type": "DNS", "ttl": 1800, "dns_main_list": [], "dns_sub_list": []}}})

        provider = DynadotDNSProvider(credentials=self.credentials, opener=opener)
        provider.get_hosts("example.test")

        self.assertIn("X-Request-ID", seen)
        self.assertNotIn("X-request-id", seen)
        # The signature must be over the id we actually sent.
        self.assertIn("X-Signature", seen)

    def test_the_signed_request_id_is_the_one_transmitted(self):
        # Signing one value and sending another is the failure above, restated.
        seen = {}

        def opener(request, timeout=None):
            seen.update(dict(request.header_items()))
            return FakeResponse({"code": 200, "data": {"glue_info": {"glue_type": "DNS", "ttl": 1800, "dns_main_list": [], "dns_sub_list": []}}})

        provider = DynadotDNSProvider(
            credentials=self.credentials,
            opener=opener,
            request_id_factory=lambda: "fixed-request-id",
        )
        provider.get_hosts("example.test")

        expected = dynadot_signature(
            "test-key",
            "test-secret",
            "/restful/v2/domains/example.test/records",
            "fixed-request-id",
        )
        self.assertEqual("fixed-request-id", seen["X-Request-ID"])
        self.assertEqual(expected, seen["X-Signature"])

    def test_the_socket_receives_the_exact_header_name(self):
        """Assert on the wire, not on the Request object.

        The previous attempt at this bug checked Request.header_items() and
        passed, while urllib went on to title-case every name inside do_open, so
        X-Request-ID still left as X-Request-Id and nothing changed. A data
        structure that holds the right string is not evidence that the right
        string was sent.
        """
        import http.client as http_client
        from ampg import dynadot_dns

        captured = {}

        class FakeConnection:
            def __init__(self, host, port=None, timeout=None):
                pass

            def request(self, method, target, body=None, headers=None):
                captured.update(headers or {})

            def getresponse(self):
                class Response:
                    status, reason, headers = 200, "OK", {}

                    def read(self):
                        return json.dumps(
                            {
                                "code": 200,
                                "data": {
                                    "glue_info": {
                                        "glue_type": "DNS",
                                        "ttl": 1800,
                                        "dns_main_list": [],
                                        "dns_sub_list": [],
                                    }
                                },
                            }
                        ).encode()

                return Response()

            def close(self):
                pass

        original = http_client.HTTPSConnection
        http_client.HTTPSConnection = FakeConnection
        try:
            provider = DynadotDNSProvider(credentials=self.credentials)
            provider.get_hosts("example.test")
        finally:
            http_client.HTTPSConnection = original

        self.assertIn("X-Request-ID", captured)
        self.assertNotIn("X-Request-Id", captured)
        self.assertNotIn("X-request-id", captured)

    def test_a_string_zone_ttl_is_accepted_because_dynadot_sends_one(self):
        """A live zone returned ttl as "300".

        The read path required an int and rejected every Dynadot zone, while the
        write path already coerced the same value with int(record.ttl). Reading
        was stricter than writing, which is the wrong way round: it made zones
        unreadable that we were perfectly capable of writing.
        """
        from ampg.dynadot_dns import _zone_ttl

        self.assertEqual(300, _zone_ttl("300"))
        self.assertEqual(1800, _zone_ttl(" 1800 "))
        self.assertEqual(300, _zone_ttl(300))

    def test_a_ttl_that_is_not_a_whole_number_of_seconds_is_refused(self):
        from ampg.dynadot_dns import _zone_ttl

        for value in ("", "abc", "300.0", None, 3.5, [], {}):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    _zone_ttl(value)

    def test_a_bool_is_not_a_ttl(self):
        # True is an int in Python and would otherwise be read as 1, then
        # rejected for being out of range rather than for being a bool.
        from ampg.dynadot_dns import _zone_ttl

        with self.assertRaises(RuntimeError):
            _zone_ttl(True)

    def test_the_range_still_holds_after_coercion(self):
        from ampg.dynadot_dns import _zone_ttl

        for value in ("59", "86401", 59, 86401):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    _zone_ttl(value)
        self.assertEqual(60, _zone_ttl("60"))
        self.assertEqual(86400, _zone_ttl("86400"))

    def test_a_real_zone_response_reads_end_to_end(self):
        """Shaped from an actual suchshop.lol response, not from the docs.

        Two things only a live zone showed. The TTL arrives as a string, and the
        records use record_value1 while the write path uses value1, so the
        reader knew only the spelling it never receives. Either one alone makes
        every Dynadot zone unreadable, and the second was hidden behind the
        first.
        """
        def opener(request, timeout=None):
            return FakeResponse({
                "code": 200,
                "data": {"glue_info": {
                    "glue_type": "DNS",
                    "ttl": "300",
                    "dns_main_list": [
                        {"record_type": "stealth", "record_value1": "mail.example.test",
                         "record_value2": "10"},
                        {"record_type": "txt",
                         "record_value1": "v=spf1 mx include:spf-c.mailbaby.net -all"},
                        {"record_type": "a", "record_value1": "203.0.113.10"},
                    ],
                    "dns_sub_list": [
                        {"record_type": "a", "record_value1": "203.0.113.11", "sub_host": "mail"},
                        {"record_type": "mx", "record_value1": "mail.example.test",
                         "record_value2": "10", "sub_host": "mail"},
                        {"record_type": "txt", "record_value1": "v=DKIM1;k=rsa;p=AAAA",
                         "sub_host": "modoboa._domainkey"},
                    ],
                }},
            })

        provider = DynadotDNSProvider(credentials=self.credentials, opener=opener)
        snapshot = provider.get_hosts("example.test")

        self.assertEqual(6, len(snapshot.records), "no record may be dropped")
        by_name = {(r.name, r.type): r for r in snapshot.records}
        # A full-zone write sends back everything read, so a value lost here is
        # a record deleted from a live zone.
        self.assertEqual("203.0.113.10", by_name[("@", "A")].value)
        self.assertEqual("v=DKIM1;k=rsa;p=AAAA", by_name[("modoboa._domainkey", "TXT")].value)
        self.assertEqual("mail.example.test", by_name[("mail", "MX")].value)
        self.assertEqual(10, by_name[("mail", "MX")].mx_pref)
        self.assertIn(("@", "STEALTH"), by_name, "an unusual type is still a record")

    def test_the_write_spelling_is_still_accepted(self):
        # Kept so the two spellings cannot quietly become one.
        def opener(request, timeout=None):
            return FakeResponse({
                "code": 200,
                "data": {"glue_info": {
                    "glue_type": "DNS", "ttl": 1800,
                    "dns_main_list": [{"record_type": "txt", "value1": "v=spf1 -all"}],
                    "dns_sub_list": [],
                }},
            })

        provider = DynadotDNSProvider(credentials=self.credentials, opener=opener)
        self.assertEqual("v=spf1 -all", provider.get_hosts("example.test").records[0].value)

    def test_mixed_ttl_and_broad_source_allowlist_fail_closed(self):
        provider = DynadotDNSProvider(credentials=self.credentials)
        with self.assertRaisesRegex(ValueError, "one observed"):
            provider.set_hosts(
                "example.test",
                (
                    ProviderDNSRecord("@", "A", "192.0.2.1", 300),
                    ProviderDNSRecord("www", "A", "192.0.2.1", 1800),
                ),
                mail_policy="preserve",
            )
        self.credentials.write_text(
            self.credentials.read_text().replace("192.0.2.10/32", "192.0.2.0/24")
        )
        with self.assertRaisesRegex(ValueError, "IPv4 /32"):
            DynadotDNSProvider(credentials=self.credentials)


if __name__ == "__main__":
    unittest.main()
