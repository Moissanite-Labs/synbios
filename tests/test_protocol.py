import json
import unittest
from synbios.protocol import discovery_document, openapi_document


class ProtocolTests(unittest.TestCase):
    def test_discovery_is_public_and_explicit_about_authority(self):
        document = discovery_document()
        self.assertFalse(document["authority"]["external_actions"])
        self.assertFalse(document["authority"]["training_consent"])
        self.assertTrue(document["local_only"])
        json.dumps(document)

    def test_schema_has_authenticated_commands_and_public_discovery(self):
        schema = openapi_document()
        self.assertEqual(schema["security"], [{"bearerAuth": []}])
        self.assertEqual(schema["paths"]["/.well-known/synbios.json"]["get"]["security"], [])
        self.assertIn("/api/commands/review.create", schema["paths"])
        json.dumps(schema)
