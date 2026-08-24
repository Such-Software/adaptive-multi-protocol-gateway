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
        self.assertEqual("10", body["dns_main_list"][0]["value2"])
        self.assertEqual("301", body["dns_sub_list"][0]["value2"])

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
