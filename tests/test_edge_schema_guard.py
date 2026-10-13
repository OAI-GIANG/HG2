import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from hg import edge


class EdgePayloadSchemaTests(unittest.TestCase):
    def test_existing_register_payload_shapes_remain_valid(self):
        self.assertIsNone(edge.validate_payload("/edge/register", {"device_id": "d1"}))
        self.assertIsNone(edge.validate_payload(
            "/edge/register",
            {"device_id": "phone-t", "runtime": "runtime-1", "architecture": "PHONE_PRIMARY_V1"},
        ))

    def test_existing_heartbeat_payload_shape_remains_valid(self):
        self.assertIsNone(edge.validate_payload(
            "/edge/heartbeat", {"device_id": "phone-t", "runtime": "runtime-1", "seq": 3}
        ))
        self.assertIsNone(edge.validate_payload("/edge/heartbeat", {"device_id": "d1", "seq": 0}))

    def test_non_object_is_rejected(self):
        self.assertEqual(edge.validate_payload("/edge/register", []), "INVALID_PAYLOAD")
        self.assertEqual(edge.validate_payload("/edge/register", None), "INVALID_PAYLOAD")

    def test_unknown_fields_are_rejected(self):
        self.assertEqual(
            edge.validate_payload("/edge/register", {"device_id": "d1", "unexpected": True}),
            "UNKNOWN_FIELD",
        )
        self.assertEqual(
            edge.validate_payload("/edge/heartbeat", {"device_id": "d1", "seq": 1, "architecture": "PHONE_PRIMARY_V1"}),
            "UNKNOWN_FIELD",
        )

    def test_model_key_fields_are_rejected_recursively(self):
        self.assertEqual(
            edge.validate_payload("/edge/register", {"device_id": "d1", "model_api_key": "secret"}),
            "MODEL_KEY_NOT_ACCEPTED",
        )
        self.assertEqual(
            edge.validate_payload("/edge/register", {"device_id": "d1", "metadata": [{"modelKey": "secret"}]}),
            "MODEL_KEY_NOT_ACCEPTED",
        )

    def test_string_values_are_not_scanned_as_field_names(self):
        self.assertIsNone(
            edge.validate_payload("/edge/register", {"device_id": "d1", "runtime": "text mentions model key"})
        )

    def test_fields_are_not_coerced(self):
        self.assertEqual(edge.validate_payload("/edge/register", {"device_id": 123}), "DEVICE_ID_REQUIRED")
        self.assertEqual(edge.validate_payload("/edge/register", {"device_id": "d1", "runtime": 4}), "INVALID_RUNTIME")
        self.assertEqual(edge.validate_payload("/edge/heartbeat", {"device_id": "d1", "seq": True}), "INVALID_SEQUENCE")
        self.assertEqual(edge.validate_payload("/edge/heartbeat", {"device_id": "d1", "seq": -1}), "INVALID_SEQUENCE")

    def test_bounds_and_architecture_are_checked(self):
        self.assertEqual(edge.validate_payload("/edge/register", {"device_id": "x" * 129}), "DEVICE_ID_TOO_LONG")
        self.assertEqual(edge.validate_payload("/edge/register", {"device_id": "d1", "runtime": "x" * 65}), "RUNTIME_TOO_LONG")
        self.assertEqual(
            edge.validate_payload("/edge/register", {"device_id": "d1", "architecture": "OTHER"}),
            "UNSUPPORTED_ARCHITECTURE",
        )

    def test_http_handler_rejects_invalid_payload_before_state_mutation(self):
        token = "edge-schema-test-token"
        with patch.dict(os.environ, {"HG_EDGE_TOKEN": token}, clear=False):
            server = ThreadingHTTPServer(("127.0.0.1", 0), edge.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            device_id = "guard-no-mutation"
            before = dict(edge.DEVICES)
            try:
                body = json.dumps({"device_id": device_id, "extra": "not-admitted"}).encode()
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/edge/register",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                )
                try:
                    with urlopen(request, timeout=3) as response:
                        self.fail(f"unexpected HTTP {response.status}")
                except HTTPError as error:
                    with error:
                        self.assertEqual(error.code, 400)
                        self.assertEqual(json.loads(error.read().decode())["error"], "UNKNOWN_FIELD")
                self.assertEqual(edge.DEVICES, before)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_handler_rejects_duplicate_json_keys(self):
        token = "edge-schema-test-token"
        with patch.dict(os.environ, {"HG_EDGE_TOKEN": token}, clear=False):
            server = ThreadingHTTPServer(("127.0.0.1", 0), edge.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            before = dict(edge.DEVICES)
            try:
                body = b'{"device_id":"first","device_id":"second"}'
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/edge/register",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                )
                try:
                    with urlopen(request, timeout=3) as response:
                        self.fail(f"unexpected HTTP {response.status}")
                except HTTPError as error:
                    with error:
                        self.assertEqual(error.code, 400)
                        self.assertEqual(json.loads(error.read().decode())["error"], "DUPLICATE_JSON_KEY")
                self.assertEqual(edge.DEVICES, before)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


    def test_http_handler_rejects_non_standard_json_constants(self):
        token = "edge-schema-test-token"
        with patch.dict(os.environ, {"HG_EDGE_TOKEN": token}, clear=False):
            server = ThreadingHTTPServer(("127.0.0.1", 0), edge.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            before = dict(edge.DEVICES)
            try:
                body = b'{"device_id":"nonstandard-json","runtime":NaN}'
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/edge/register",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                )
                try:
                    with urlopen(request, timeout=3) as response:
                        self.fail(f"unexpected HTTP {response.status}")
                except HTTPError as error:
                    with error:
                        self.assertEqual(error.code, 400)
                        self.assertEqual(json.loads(error.read().decode())["error"], "INVALID_JSON")
                self.assertEqual(edge.DEVICES, before)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
