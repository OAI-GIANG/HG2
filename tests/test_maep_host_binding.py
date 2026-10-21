import tempfile
import unittest
from hg.auth import BearerAuthenticator
from hg.sqlite_state import SQLiteStateStore
from hg.workflow_store_adapter import CanonicalWorkflowAdapter
from hg.maep_host_binding import MaepHostBinding, MaepHostBindingError


class MaepHostBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SQLiteStateStore(self.tmp.name, clock=lambda: 100.0)
        self.principal = BearerAuthenticator(
            'host-binding-test', {'audit.append', 'brain.request'}, principal_id='owner'
        ).authenticate('Bearer host-binding-test')
        self.adapter = CanonicalWorkflowAdapter(
            self.store, principal=self.principal, actor_id='owner', clock=lambda: 100.0
        )
        self.handler = {'action': 'brain.request', 'prepare': lambda s, c: {'passed': True, 'evidence_ids': ['entry-1']},
                        'run': lambda s, c: {'status': 'BLOCKED', 'reason': 'test-only'}}
        self.authorizer = lambda a, c: (True, 'host-policy:unit-test')
        self.verifier = lambda ids, c: (True, 'evidence:unit-test')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def binding(self, **overrides):
        args = dict(adapter=self.adapter, phase_actions={'S0': 'brain.request'},
                    handler_registry={'brain.request': self.handler},
                    action_scopes={'brain.request': 'brain.request'},
                    authorizer=self.authorizer, evidence_verifier=self.verifier)
        args.update(overrides)
        return MaepHostBinding(**args)

    def test_build_uses_existing_canonical_adapter_and_static_registry(self):
        binding = self.binding()
        engine = binding.build_orchestrator()
        self.assertIs(engine.store.store, self.store)
        self.assertIs(engine.handlers['S0']['run'], self.handler['run'])

    def test_unknown_phase_and_unregistered_handler_fail_closed(self):
        with self.assertRaisesRegex(MaepHostBindingError, 'PHASE_ALLOWLIST_INVALID'):
            self.binding(phase_actions={'S99': 'brain.request'})
        with self.assertRaisesRegex(MaepHostBindingError, 'REGISTERED_HANDLER_INVALID'):
            self.binding(handler_registry={})

    def test_missing_scope_or_callback_fails_closed(self):
        with self.assertRaisesRegex(MaepHostBindingError, 'ACTION_SCOPE_NOT_GRANTED'):
            self.binding(action_scopes={'brain.request': 'provider.invoke'})
        with self.assertRaisesRegex(MaepHostBindingError, 'REAL_AUTHORIZER_REQUIRED'):
            self.binding(authorizer=None)
        with self.assertRaisesRegex(MaepHostBindingError, 'REAL_EVIDENCE_VERIFIER_REQUIRED'):
            self.binding(evidence_verifier=None)

    def test_authorization_rejects_prompt_invented_action_and_invalid_host_result(self):
        binding = self.binding()
        self.assertEqual(binding._authorize('shell.exec', {'phase_id': 'S0'})[0], False)
        self.assertEqual(binding._authorize('brain.request', {'phase_id': 'S1'})[0], False)
        bad = self.binding(authorizer=lambda a, c: {'allow': True})
        self.assertEqual(bad._authorize('brain.request', {'phase_id': 'S0'}),
                         (False, 'MAEP_HOST_AUTHORIZER_INVALID_RESPONSE'))

    def test_evidence_verifier_errors_and_malformed_results_fail_closed(self):
        broken = self.binding(evidence_verifier=lambda ids, ctx: (_ for _ in ()).throw(RuntimeError()))
        self.assertEqual(broken._verify_evidence(['e1'], {}), (False, 'MAEP_HOST_EVIDENCE_VERIFIER_ERROR'))
        malformed = self.binding(evidence_verifier=lambda ids, ctx: True)
        self.assertEqual(malformed._verify_evidence(['e1'], {}),
                         (False, 'MAEP_HOST_EVIDENCE_VERIFIER_INVALID_RESPONSE'))


if __name__ == '__main__':
    unittest.main()
