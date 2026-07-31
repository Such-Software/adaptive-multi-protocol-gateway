from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ampg.dns import DNSZoneSnapshot, ProviderDNSRecord
from ampg.dns_manifest import (
    load_dns_manifest,
    merge_dns_manifest_records,
    reconcile_dns_manifest,
)


def manifest_document():
    return {
        "contract_version": 1,
        "app_id": "bloomword",
        "zone": "bloomword.earth",
        "provider": "namecheap",
        "preserve_unmanaged": True,
        "protected_names": ["@"],
        "records": [
            {
                "name": "shop",
                "type": "A",
                "value": "94.72.115.61",
                "ttl": 300,
                "replace": "all",
                "conflict_types": ["CNAME", "ALIAS"],
            },
            {
                "name": "shop",
                "type": "TXT",
                "value": "v=spf1 include:mail.baby ~all",
                "ttl": 300,
                "replace": "value_prefix",
                "match_value_prefix": "v=spf1",
            },
        ],
    }


class FakeProvider:
    name = "namecheap"
    backup_format = "xml"

    def __init__(self, records):
        self.records = tuple(records)
        self.writes = 0

    def get_hosts(self, zone):
        return DNSZoneSnapshot(
            "namecheap", zone, "<zone />", self.records, "ok", "ok"
        )

    def set_hosts(self, zone, records, *, mail_policy):
        self.writes += 1
        self.records = tuple(records)


class DNSManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "dns.json"
        self.path.write_text(
            json.dumps(manifest_document()), encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_merge_preserves_apex_mail_and_unrelated_shop_txt(self):
        manifest = load_dns_manifest(self.path)
        existing = (
            ProviderDNSRecord("@", "A", "153.75.248.86", 1800),
            ProviderDNSRecord(
                "@", "MX", "eforward1.registrar-servers.com.", 1800, 10
            ),
            ProviderDNSRecord(
                "@",
                "TXT",
                "v=spf1 include:spf.efwd.registrar-servers.com ~all",
                1800,
            ),
            ProviderDNSRecord("shop", "CNAME", "parking.example.", 1800),
            ProviderDNSRecord("shop", "TXT", "verification=keep", 1800),
            ProviderDNSRecord("shop", "TXT", "v=spf1 -all", 1800),
        )
        merged = merge_dns_manifest_records(existing, manifest.records)
        identities = {
            (record.name, record.type, record.value) for record in merged
        }
        self.assertIn(("@", "A", "153.75.248.86"), identities)
        self.assertIn(
            ("@", "MX", "eforward1.registrar-servers.com."), identities
        )
        self.assertIn(("shop", "TXT", "verification=keep"), identities)
        self.assertNotIn(("shop", "CNAME", "parking.example."), identities)
        self.assertNotIn(("shop", "TXT", "v=spf1 -all"), identities)
        self.assertIn(("shop", "A", "94.72.115.61"), identities)

    def test_protected_apex_cannot_be_managed(self):
        document = manifest_document()
        document["records"][0]["name"] = "@"
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "protected"):
            load_dns_manifest(self.path)

    def test_unresolved_values_are_rejected(self):
        document = manifest_document()
        document["records"][0]["value"] = "{{ prod_ip }}"
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unresolved"):
            load_dns_manifest(self.path)

    def test_connected_plan_is_read_only_and_apply_is_idempotent(self):
        manifest = load_dns_manifest(self.path)
        provider = FakeProvider(
            [ProviderDNSRecord("@", "A", "153.75.248.86", 1800)]
        )
        planned = reconcile_dns_manifest(manifest, provider)
        self.assertEqual("planned", planned["status"])
        self.assertEqual(0, provider.writes)
        backup_dir = Path(self.temporary.name) / "backups"
        applied = reconcile_dns_manifest(
            manifest, provider, apply=True, backup_dir=backup_dir
        )
        self.assertEqual("applied", applied["status"])
        self.assertEqual(1, provider.writes)
        second = reconcile_dns_manifest(
            manifest, provider, apply=True, backup_dir=backup_dir
        )
        self.assertEqual("verified", second["status"])
        self.assertEqual(1, provider.writes)

    def test_dynadot_requires_observed_zone_ttl(self):
        document = manifest_document()
        document["provider"] = "dynadot"
        document["records"][0]["conflict_types"] = ["CNAME", "ANAME"]
        self.path.write_text(json.dumps(document), encoding="utf-8")
        manifest = load_dns_manifest(self.path)
        provider = FakeProvider([])
        provider.name = "dynadot"
        with self.assertRaisesRegex(Exception, "observed zone TTL"):
            reconcile_dns_manifest(manifest, provider)

    def test_provider_credentials_must_match_manifest(self):
        manifest = load_dns_manifest(self.path)
        provider = FakeProvider([])
        provider.name = "dynadot"
        with self.assertRaisesRegex(Exception, "do not match"):
            reconcile_dns_manifest(manifest, provider)

    def test_dynadot_apply_uses_json_backup_and_is_idempotent(self):
        document = manifest_document()
        document["provider"] = "dynadot"
        document["records"][0]["conflict_types"] = ["CNAME", "ANAME"]
        self.path.write_text(json.dumps(document), encoding="utf-8")
        manifest = load_dns_manifest(self.path)

        class FakeDynadot(FakeProvider):
            name = "dynadot"
            backup_format = "json"

            def get_hosts(self, zone):
                return DNSZoneSnapshot(
                    self.name,
                    zone,
                    '{"zone":"snapshot"}\n',
                    self.records,
                    "ok",
                    "ok",
                    300,
                )

        provider = FakeDynadot(
            [ProviderDNSRecord("@", "A", "153.75.248.86", 300)]
        )
        backup_dir = Path(self.temporary.name) / "backups"
        result = reconcile_dns_manifest(
            manifest, provider, apply=True, backup_dir=backup_dir
        )
        self.assertEqual("applied", result["status"])
        self.assertTrue(result["backup_path"].endswith(".json"))
        self.assertEqual(1, provider.writes)
        second = reconcile_dns_manifest(
            manifest, provider, apply=True, backup_dir=backup_dir
        )
        self.assertEqual("verified", second["status"])
        self.assertEqual(1, provider.writes)


if __name__ == "__main__":
    unittest.main()
