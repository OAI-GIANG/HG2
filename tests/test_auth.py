import os
import unittest
from unittest.mock import patch
from hg.auth import BearerAuthenticator, AuthenticatedPrincipal


class BearerAuthenticatorTests(unittest.TestCase):
    def setUp(self):
        self.token = "fixture-token-never-a-real-secret"
        self.auth = BearerAuthenticator(self.token, {"provider.invoke", "session.create"})

    def test_valid_bearer_returns_scoped_principal(self):
        principal = self.auth.authenticate("Bearer " + self.token)
        self.assertIsInstance(principal, AuthenticatedPrincipal)
        self.assertTrue(principal.allows("provider.invoke"))
        self.assertTrue(principal.allows("session.create"))
        self.assertFalse(principal.allows("shell.exec"))

    def test_missing_malformed_and_wrong_headers_fail_closed(self):
        for header in (None, "", "Basic " + self.token, "Bearer", "Bearer wrong",
                       "Bearer " + self.token + " extra", "Bearer " + self.token + "\n"):
            with self.subTest(header=header):
                self.assertIsNone(self.auth.authenticate(header))

    def test_unconfigured_token_fails_closed(self):
        auth = BearerAuthenticator("", {"provider.invoke", "session.create"})
        self.assertIsNone(auth.authenticate("Bearer any-token"))

    def test_unknown_scope_invalidates_all_scopes(self):
        auth = BearerAuthenticator(self.token, {"provider.invoke", "shell.exec"})
        self.assertEqual(auth.scopes, frozenset())
        self.assertIsNone(auth.authenticate("Bearer " + self.token))

    def test_default_scope_is_provider_only(self):
        auth = BearerAuthenticator(self.token)
        principal = auth.authenticate("Bearer " + self.token)
        self.assertTrue(principal.allows("provider.invoke"))
        self.assertFalse(principal.allows("session.create"))

    def test_environment_configuration_is_data_and_repr_redacts_token(self):
        with patch.dict(os.environ, {"HG_AUTH_TOKEN": self.token, "HG_AUTH_SCOPES": "provider.invoke,session.create", "HG_AUTH_PRINCIPAL_ID": "env-user"}, clear=True):
            auth = BearerAuthenticator.from_env()
        principal = auth.authenticate("Bearer " + self.token)
        self.assertIsNotNone(principal)
        self.assertEqual(principal.principal_id, "env-user")
        self.assertNotIn(self.token, repr(auth))
        self.assertNotIn(self.token, repr(principal))

    def test_invalid_environment_scope_fails_closed(self):
        with patch.dict(os.environ, {"HG_AUTH_TOKEN": self.token, "HG_AUTH_SCOPES": "provider.invoke,shell.exec"}, clear=True):
            auth = BearerAuthenticator.from_env()
        self.assertIsNone(auth.authenticate("Bearer " + self.token))

    def test_missing_principal_id_is_not_mutation_identity(self):
        from hg.policy import authorize_service_mutation
        principal = self.auth.authenticate("Bearer " + self.token)
        self.assertEqual(authorize_service_mutation("session.create", principal).reason, "PRINCIPAL_ID_REQUIRED")
        named = BearerAuthenticator(self.token, {"session.create"}, principal_id="alice").authenticate("Bearer " + self.token)
        self.assertTrue(authorize_service_mutation("session.create", named).allowed)

    def test_principal_cannot_be_forged_without_internal_seal(self):
        forged = AuthenticatedPrincipal(frozenset({"provider.invoke", "session.create"}), object())
        self.assertFalse(forged.allows("provider.invoke"))
        self.assertFalse(forged.allows("session.create"))


if __name__ == "__main__":
    unittest.main()
