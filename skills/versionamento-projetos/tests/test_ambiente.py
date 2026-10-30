"""Provisioning decisions with mocked GitHub and an isolated real Git remote test."""
from pathlib import Path
import importlib.util
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location('repository_environment', SCRIPTS / 'ambiente.py')
env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(env)
OWNER = 'fixture-owner'
REPO = OWNER + '/fixture-project'
URL = 'https://github.com/' + REPO
REMOTE_POLICY = {'mode': 'PRIVATE_REMOTE_ALLOWED', 'source': 'DIRECT_USER_DECISION',
                 'as_of': '2026-10-29', 'create_remote': True, 'push': True}
LOCAL_POLICY = dict(REMOTE_POLICY, mode='LOCAL_ONLY', create_remote=False, push=False)


def response(status=200, body=None, code=None, stderr=''):
    content = 'HTTP/2.0 ' + str(status) + ' Fixture\nContent-Type: application/json\n\n' + json.dumps(body or {})
    return subprocess.CompletedProcess([], (0 if status == 200 else 1) if code is None else code, content, stderr)


class EnsureRemoteTests(unittest.TestCase):
    def setUp(self):
        self.project = {'id': 'fixture-project', 'repo_root': '/isolated-fixture', 'github_repo': REPO,
                        'remote': URL + '.git', 'remote_state': 'PENDING_PROVISIONING'}
        self.registry = {'github_owner': OWNER, 'projects': [self.project], 'publication_policy': copy.deepcopy(REMOTE_POLICY)}
        self.api_user = response(body={'login': OWNER})
        self.api_repos = [response(body={'private': True, 'full_name': REPO, 'html_url': URL})]
        self.create_result = subprocess.CompletedProcess([], 0, URL, '')
        self.origins = [None, None, URL + '.git']
        self.save = mock.patch.object(env, 'save', side_effect=lambda reg, project, patch: dict(project, **patch)).start()
        self.addCleanup(mock.patch.stopall)
        self.run = mock.patch.object(env, 'run', side_effect=self.fake_run).start()
        self.load = mock.patch.object(env, 'load', side_effect=lambda: copy.deepcopy(self.registry)).start()
        self.read_origin = mock.patch.object(env, 'read_origin', side_effect=lambda root: self.origins.pop(0)).start()

    def fake_run(self, args, **kwargs):
        words = [str(x) for x in args]
        if words[:3] == [str(env.GH), 'api', 'user']:
            return self.api_user
        if words[:3] == [str(env.GH), 'api', 'repos/' + REPO]:
            return self.api_repos.pop(0)
        if words[:3] == [str(env.GH), 'repo', 'create']:
            return self.create_result
        if words[0] == 'git' and words[3:6] == ['remote', 'add', 'origin']:
            return subprocess.CompletedProcess([], 0, '', '')
        raise AssertionError('unexpected command family')

    def creations(self):
        return [c for c in self.run.call_args_list if [str(x) for x in c.args[0]][1:3] == ['repo', 'create']]

    def links(self):
        return [c for c in self.run.call_args_list if [str(x) for x in c.args[0]][3:6] == ['remote', 'add', 'origin']]

    def ensure(self):
        result = env.ensure_remote(self.registry, self.project)
        self.save.assert_called_once()
        self.assertIs(self.save.call_args.args[0], self.registry)
        self.assertIs(self.save.call_args.args[1], self.project)
        self.assertTrue(set(self.save.call_args.args[2]).issubset(env.REMOTE_FIELDS))
        return result

    def test_existing_private_repository_gets_missing_origin(self):
        self.assertEqual(self.ensure()['status'], 'VERIFIED')
        self.assertEqual(len(self.creations()), 0)
        self.assertEqual(len(self.links()), 1)
        self.assertEqual(self.project['origin_state'], 'LINKED_VERIFIED')

    def test_explicit_404_allows_one_creation_then_revalidates(self):
        self.api_repos.insert(0, response(404, {'message': 'Not Found'}))
        self.assertEqual(self.ensure()['status'], 'VERIFIED')
        self.assertEqual(len(self.creations()), 1)
        self.assertEqual(len(self.links()), 1)

    def test_ambiguous_missing_lookup_does_not_create(self):
        for missing in (subprocess.CompletedProcess([], 1, '', 'Could not resolve to a Repository'),
                        response(404, {'unexpected': True}), response(500, {'message': 'Internal error'})):
            with self.subTest(status=missing.returncode):
                self.api_repos = [missing]
                self.origins = [None]
                self.save.reset_mock()
                self.assertEqual(self.ensure()['status'], 'BLOCKED')
        self.assertFalse(self.creations())
        self.assertFalse(self.links())

    def test_authentication_failure_stops_before_repo_lookup(self):
        self.api_user = response(401, {'message': 'Bad credentials'})
        self.assertEqual(self.ensure()['code'], 'GITHUB_AUTHENTICATION_FAILED')
        self.assertFalse(self.creations())
        self.assertFalse(self.links())
        self.assertEqual(len(self.run.call_args_list), 1)

    def test_wrong_account_stops_before_repo_lookup(self):
        self.api_user = response(body={'login': 'someone-else'})
        self.assertEqual(self.ensure()['code'], 'AUTHENTICATED_OWNER_MISMATCH')
        self.assertFalse(self.creations())
        self.assertFalse(self.links())

    def test_permission_failure_does_not_create(self):
        self.api_repos = [response(403, {'message': 'Forbidden'})]
        self.assertEqual(self.ensure()['code'], 'GITHUB_PERMISSION_DENIED')
        self.assertFalse(self.creations())

    def test_rate_limit_has_structured_state_and_no_retry(self):
        self.api_repos = [response(429, {'message': 'Rate limit exceeded'})]
        result = self.ensure()
        self.assertEqual(result['code'], 'GITHUB_RATE_LIMIT')
        self.assertFalse(result['retry_attempted'])
        self.assertEqual(self.project['remote_state'], 'BLOCKED_GITHUB_RATE_LIMIT')
        self.assertFalse(self.creations())
        self.assertEqual(len(self.run.call_args_list), 2)

    def test_creation_limit_has_structured_state_and_no_retry(self):
        self.api_repos = [response(404, {'message': 'Not Found'})]
        self.create_result = subprocess.CompletedProcess([], 1, '', 'Repository creation is limited. Please try later.')
        result = self.ensure()
        self.assertEqual(result['code'], 'REPOSITORY_CREATION_LIMIT')
        self.assertFalse(self.project['remote_operation']['retry_attempted'])
        self.assertEqual(len(self.creations()), 1)
        self.assertFalse(self.links())

    def test_confirmed_push_is_not_downgraded_on_rate_limit(self):
        self.project.update(remote_state='PUSH_CONFIRMED', remote_commit='a' * 40)
        self.api_repos = [response(429, {'message': 'Rate limit exceeded'})]
        self.assertEqual(self.ensure()['code'], 'GITHUB_RATE_LIMIT')
        self.assertEqual(self.project['remote_state'], 'PUSH_CONFIRMED')
        self.assertEqual(self.project['remote_commit'], 'a' * 40)

    def test_confirmed_push_is_not_downgraded_on_success(self):
        self.project.update(remote_state='PUSH_CONFIRMED', remote_commit='a' * 40)
        self.assertEqual(self.ensure()['status'], 'VERIFIED')
        self.assertEqual(self.project['remote_state'], 'PUSH_CONFIRMED')

    def test_unproven_push_state_can_be_marked_blocked(self):
        self.project.update(remote_state='PUSH_CONFIRMED')
        self.api_repos = [response(429, {'message': 'Rate limit exceeded'})]
        self.ensure()
        self.assertEqual(self.project['remote_state'], 'BLOCKED_GITHUB_RATE_LIMIT')

    def test_public_or_different_repository_is_never_linked(self):
        for payload in ({'private': False, 'full_name': REPO, 'html_url': URL},
                        {'private': True, 'full_name': OWNER + '/other', 'html_url': URL},
                        {'private': True, 'full_name': REPO, 'html_url': 'https://example.invalid/' + REPO}):
            with self.subTest(payload=payload):
                self.api_repos = [response(body=payload)]
                self.origins = [None]
                self.save.reset_mock()
                self.assertEqual(self.ensure()['status'], 'BLOCKED')
        self.assertFalse(self.links())
        self.assertFalse(self.creations())

    def test_existing_matching_ssh_origin_is_preserved(self):
        ssh = 'git@github.com:' + REPO + '.git'
        self.origins = [ssh, ssh]
        self.assertEqual(self.ensure()['status'], 'VERIFIED')
        self.assertEqual(self.project['remote'], ssh)
        self.assertFalse(self.links())

    def test_divergent_origin_blocks_before_any_github_call(self):
        self.origins = ['https://github.com/other/repository.git']
        self.assertEqual(self.ensure()['code'], 'ORIGIN_IDENTITY_MISMATCH')
        self.run.assert_not_called()

    def test_concurrent_origin_change_is_not_overwritten(self):
        self.origins = [None, 'https://github.com/other/repository.git']
        self.assertEqual(self.ensure()['code'], 'ORIGIN_IDENTITY_MISMATCH')
        self.assertFalse(self.links())

    def test_new_repository_is_not_linked_before_post_create_validation(self):
        self.api_repos = [response(404, {'message': 'Not Found'}), response(body={'private': False, 'full_name': REPO, 'html_url': URL})]
        self.assertEqual(self.ensure()['code'], 'REPOSITORY_NOT_PRIVATE')
        self.assertEqual(len(self.creations()), 1)
        self.assertFalse(self.links())

    def test_invalid_json_response_is_blocked_without_create(self):
        self.api_repos = [subprocess.CompletedProcess([], 0, 'HTTP/2.0 200 OK\n\nnot-json', '')]
        self.assertEqual(self.ensure()['code'], 'GITHUB_RESPONSE_INVALID')
        self.assertFalse(self.creations())

    def test_transport_exception_is_structured_and_does_not_create(self):
        self.run.side_effect = subprocess.TimeoutExpired('redacted-command', 120)
        self.assertEqual(self.ensure()['code'], 'GITHUB_TRANSPORT_OR_AMBIGUOUS_ERROR')
        self.assertFalse(self.creations())

    def test_rate_failure_does_not_persist_raw_response(self):
        private_marker = 'synthetic-private-response-value'
        self.api_repos = [response(429, {'message': 'Rate limit exceeded', 'detail': private_marker}, stderr=private_marker)]
        result = self.ensure()
        self.assertNotIn(private_marker, json.dumps(result) + json.dumps(self.registry))

    def test_credentialed_or_divergent_registry_url_blocks_before_github(self):
        self.project['remote'] = 'https://synthetic-password@github.com/' + REPO + '.git'
        self.assertEqual(self.ensure()['code'], 'REGISTRY_REMOTE_MISMATCH')
        self.run.assert_not_called()

    def test_cli_stops_account_batch_after_creation_or_rate_limit(self):
        self.registry['projects'].append(dict(self.project, id='second-project'))
        blocked = {'id': self.project['id'], 'status': 'BLOCKED', 'code': 'REPOSITORY_CREATION_LIMIT'}
        with mock.patch.object(env, 'load', return_value=self.registry), \
             mock.patch.object(env, 'ensure_remote', return_value=blocked) as ensure, \
             mock.patch.object(sys, 'argv', ['ambiente.py', 'ensure-remote']), \
             mock.patch('builtins.print') as printed:
            self.assertEqual(env.main(), 1)
        ensure.assert_called_once_with(self.registry, self.project)
        report = json.loads(printed.call_args.args[0])
        self.assertEqual(report['results'][1]['status'], 'NOT_ATTEMPTED')
        self.assertEqual(report['results'][1]['code'], 'ACCOUNT_LIMIT_STOP')
        self.assertEqual(self.registry['projects'][1]['remote_state'], 'PENDING_PROVISIONING')

    def test_local_only_blocks_before_any_git_or_github_call(self):
        self.registry['publication_policy'] = copy.deepcopy(LOCAL_POLICY)
        self.assertEqual(self.ensure()['code'], 'PUBLICATION_LOCAL_ONLY')
        self.run.assert_not_called()
        self.read_origin.assert_not_called()

    def test_local_only_preserves_confirmed_history_and_remote(self):
        self.registry['publication_policy'] = copy.deepcopy(LOCAL_POLICY)
        self.project.update(remote_state='PUSH_CONFIRMED', remote_commit='a' * 40,
                            github_url=URL, origin_state='LINKED_VERIFIED')
        before = {key: self.project[key] for key in ('remote_state', 'remote_commit', 'remote', 'github_url', 'origin_state')}
        self.assertEqual(self.ensure()['code'], 'PUBLICATION_LOCAL_ONLY')
        self.assertEqual({key: self.project[key] for key in before}, before)
        self.run.assert_not_called()

    def test_local_only_records_decision_without_rewriting_remote_existence_state(self):
        self.registry['publication_policy'] = copy.deepcopy(LOCAL_POLICY)
        self.project['remote_state'] = 'PRIVATE_REPOSITORY_VERIFIED'
        self.assertEqual(self.ensure()['code'], 'PUBLICATION_LOCAL_ONLY')
        self.assertEqual(self.project['remote_state'], 'PRIVATE_REPOSITORY_VERIFIED')
        self.assertEqual(self.project['remote_operation']['code'], 'PUBLICATION_LOCAL_ONLY')

    def test_missing_or_invalid_policy_never_authorizes_github(self):
        for value in (None, dict(LOCAL_POLICY, push=True), dict(LOCAL_POLICY, as_of='2026-99-99'), {'mode': 'unknown'}):
            with self.subTest(value=value):
                if value is None:
                    self.registry.pop('publication_policy', None)
                else:
                    self.registry['publication_policy'] = value
                self.assertEqual(env.ensure_remote(self.registry, self.project)['status'], 'BLOCKED')
        self.run.assert_not_called()
        self.save.assert_not_called()

    def test_unavailable_current_registry_blocks_without_github_or_save(self):
        self.load.side_effect = env.RegistryError('REGISTRY_UNREADABLE_OR_INVALID')
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'], 'REGISTRY_UNREADABLE_OR_INVALID')
        self.run.assert_not_called()
        self.save.assert_not_called()

    def test_new_local_only_decision_during_account_check_stops_next_github_call(self):
        original = self.fake_run
        def change_policy(args, **kwargs):
            result = original(args, **kwargs)
            self.registry['publication_policy'] = copy.deepcopy(LOCAL_POLICY)
            return result
        self.run.side_effect = change_policy
        self.assertEqual(self.ensure()['code'], 'PUBLICATION_LOCAL_ONLY')
        self.assertEqual(len(self.run.call_args_list), 1)
        self.assertFalse(self.creations())

    def test_local_only_without_github_metadata_blocks_without_persisting_or_calls(self):
        self.registry['publication_policy'] = copy.deepcopy(LOCAL_POLICY)
        self.project.pop('github_repo')
        self.project['remote'] = None
        self.project.pop('remote_state')
        before = copy.deepcopy(self.registry)
        result = env.ensure_remote(self.registry, self.project)
        self.assertEqual(result['code'], 'PUBLICATION_LOCAL_ONLY')
        self.assertEqual(result['persistence'], 'SKIPPED_NO_REMOTE_BINDING')
        self.assertEqual(self.registry, before)
        self.run.assert_not_called()
        self.read_origin.assert_not_called()
        self.save.assert_not_called()


class SelectedEnsureRemoteTests(unittest.TestCase):
    fake_run = EnsureRemoteTests.fake_run
    creations = EnsureRemoteTests.creations
    links = EnsureRemoteTests.links

    def setUp(self):
        EnsureRemoteTests.setUp(self)
        self.project['repo_root'] = str(Path(tempfile.gettempdir()).resolve() / 'selected-fixture')
        self.selection = {'id': 'selected-fixture', 'project_id': self.project['id'],
                          'repository': REPO, 'visibility': 'private', 'create_remote': False,
                          'update': {'local_sha': 'a' * 40, 'remote_ref': 'refs/heads/main',
                                     'expected_remote_sha': '0' * 40}}
        self.registry['publication_policy'] = dict(LOCAL_POLICY, mode='PRIVATE_SELECTED', selections=[self.selection])

    def test_existing_private_selected_repository_can_be_verified_without_creation(self):
        self.assertEqual(env.ensure_remote(self.registry, self.project)['status'], 'VERIFIED')
        self.assertFalse(self.creations())
        self.assertEqual(len(self.links()), 1)

    def test_absent_selected_repository_is_not_created_without_individual_permission(self):
        self.api_repos = [response(404, {'message': 'Not Found'})]
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'], 'REMOTE_CREATION_NOT_SELECTED')
        self.assertFalse(self.creations())
        self.assertFalse(self.links())

    def test_selected_creation_is_private_and_forces_github_host(self):
        self.selection['create_remote'] = True
        self.api_repos.insert(0, response(404, {'message': 'Not Found'}))
        with mock.patch.dict(env.os.environ, {'GH_HOST': 'enterprise.invalid'}):
            self.assertEqual(env.ensure_remote(self.registry, self.project)['status'], 'VERIFIED')
        creation = self.creations()[0]
        self.assertIn('--private', creation.args[0])
        self.assertNotIn('--public', creation.args[0])
        self.assertEqual(creation.kwargs['env']['GH_HOST'], 'github.com')
        for call in self.run.call_args_list:
            if [str(x) for x in call.args[0]][1:2] == ['api']:
                self.assertEqual(call.args[0][-2:], ['--hostname', 'github.com'])

    def test_project_without_selection_never_calls_git_or_github(self):
        self.registry['publication_policy']['selections'] = []
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'], 'PUBLICATION_NOT_SELECTED')
        self.read_origin.assert_not_called()
        self.run.assert_not_called()
        self.save.assert_not_called()

    def test_changed_project_identity_cannot_reuse_selection(self):
        self.registry['projects'] = [dict(self.project, github_repo=OWNER + '/other')]
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'], 'PUBLICATION_SELECTION_IDENTITY_MISMATCH')
        self.run.assert_not_called()

    def test_selected_cli_requires_explicit_project_instead_of_batch(self):
        with mock.patch.object(sys, 'argv', ['ambiente.py', 'ensure-remote']), mock.patch('builtins.print') as printed:
            self.assertEqual(env.main(), 1)
        self.assertEqual(json.loads(printed.call_args.args[0])['code'], 'EXPLICIT_PROJECT_REQUIRED')
        self.run.assert_not_called()

    def test_malformed_policy_cli_fails_closed_before_git_or_github(self):
        for policy in (None, 'invalid-policy', {}):
            with self.subTest(policy=policy):
                self.registry['publication_policy'] = policy
                with mock.patch.object(sys, 'argv', ['ambiente.py', 'ensure-remote']), mock.patch('builtins.print') as printed:
                    self.assertEqual(env.main(), 2)
                self.assertEqual(json.loads(printed.call_args.args[0])['status'], 'BLOCKED')
        self.run.assert_not_called()
        self.read_origin.assert_not_called()

    def test_revoked_selection_stops_before_second_remote_read(self):
        original = self.fake_run
        def revoke(args, **kwargs):
            result = original(args, **kwargs)
            self.registry['publication_policy']['selections'] = []
            return result
        self.run.side_effect = revoke
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'], 'PUBLICATION_NOT_SELECTED')
        self.assertEqual(len(self.run.call_args_list), 1)
        self.assertFalse(self.creations())
        self.assertFalse(self.links())

    def test_selected_public_repository_is_never_linked(self):
        self.api_repos = [response(body={'private': False, 'full_name': REPO, 'html_url': URL})]
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'], 'REPOSITORY_NOT_PRIVATE')
        self.assertFalse(self.links())


class RegistryPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='registry-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'registry.local.json'
        self.project = {'id': 'fixture-project', 'repo_root': '/isolated-fixture', 'github_repo': REPO,
                        'remote': URL + '.git', 'remote_state': 'PENDING_PROVISIONING',
                        'last_task_commit': 'initial-task'}
        self.registry = {'github_owner': OWNER, 'projects': [self.project, {'id': 'other', 'note': 'initial'}],
                         'unrelated_metadata': {'note': 'initial'}, 'publication_policy': copy.deepcopy(REMOTE_POLICY)}
        self.path.write_text(json.dumps(self.registry), encoding='utf-8')
        self.registry_patch = mock.patch.object(env, 'REGISTRY', self.path)
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)
        self.stale = env.load()

    def write_latest(self, registry):
        self.path.write_text(json.dumps(registry), encoding='utf-8')

    def patch(self, values):
        return env.save(self.stale, self.stale['projects'][0], values)

    def test_preserves_concurrent_task_fields_other_projects_and_top_level(self):
        current = copy.deepcopy(self.registry)
        current['projects'][0]['last_task_commit'] = 'concurrent-task'
        current['projects'][0]['last_task_branch'] = 'concurrent-branch'
        current['projects'][1]['note'] = 'concurrent-other-project'
        current['projects'].append({'id': 'added-by-other-chat', 'note': 'new'})
        current['unrelated_metadata']['note'] = 'concurrent-metadata'
        self.write_latest(current)
        self.patch({'origin_state': 'LINKED_VERIFIED'})
        saved = env.load()
        self.assertEqual(saved['projects'][0]['last_task_commit'], 'concurrent-task')
        self.assertEqual(saved['projects'][0]['last_task_branch'], 'concurrent-branch')
        self.assertEqual(saved['projects'][1], current['projects'][1])
        self.assertEqual(saved['projects'][2], current['projects'][2])
        self.assertEqual(saved['unrelated_metadata'], current['unrelated_metadata'])
        self.assertEqual(saved['projects'][0]['origin_state'], 'LINKED_VERIFIED')

    def test_concurrent_confirmed_push_survives_block_or_verification_patch(self):
        for state in ('BLOCKED_GITHUB_RATE_LIMIT', 'PRIVATE_REPOSITORY_VERIFIED'):
            with self.subTest(state=state):
                current = copy.deepcopy(self.registry)
                current['projects'][0].update(remote_state='PUSH_CONFIRMED', remote_commit='b' * 40)
                self.write_latest(current)
                updated = self.patch({'remote_state': state, 'remote_operation': {'status': 'BLOCKED'}})
                self.assertEqual(updated['remote_state'], 'PUSH_CONFIRMED')
                self.assertEqual(updated['remote_commit'], 'b' * 40)
                self.assertEqual(env.load()['projects'][0]['remote_state'], 'PUSH_CONFIRMED')

    def test_destination_changes_are_conflicts_and_never_overwritten(self):
        for key, value in (('github_repo', OWNER + '/different'), ('repo_root', '/different-root'),
                           ('remote', 'https://github.com/' + OWNER + '/different.git'),
                           ('github_url', 'https://github.com/' + OWNER + '/different'), ('visibility', 'public')):
            with self.subTest(key=key):
                current = copy.deepcopy(self.registry)
                current['projects'][0][key] = value
                self.write_latest(current)
                before = self.path.read_bytes()
                with self.assertRaises(env.RegistryError) as failure:
                    self.patch({'origin_state': 'LINKED_VERIFIED'})
                self.assertEqual(failure.exception.code, 'REGISTRY_DESTINATION_CONFLICT')
                self.assertEqual(self.path.read_bytes(), before)

    def test_account_or_default_visibility_change_is_conflict(self):
        for key, value in (('github_owner', 'other-owner'), ('visibility_default', 'public')):
            with self.subTest(key=key):
                current = copy.deepcopy(self.registry)
                current[key] = value
                self.write_latest(current)
                before = self.path.read_bytes()
                with self.assertRaises(env.RegistryError):
                    self.patch({'origin_state': 'LINKED_VERIFIED'})
                self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_registry_is_not_replaced_with_empty_state(self):
        self.path.write_text('{corrupted', encoding='utf-8')
        with self.assertRaises(env.RegistryError) as failure:
            self.patch({'origin_state': 'LINKED_VERIFIED'})
        self.assertEqual(failure.exception.code, 'REGISTRY_UNREADABLE_OR_INVALID')
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{corrupted')

    def test_missing_registry_is_not_created_from_stale_snapshot(self):
        self.path.unlink()
        with self.assertRaises(env.RegistryError):
            self.patch({'origin_state': 'LINKED_VERIFIED'})
        self.assertFalse(self.path.exists())

    def test_busy_lock_fails_immediately_without_overwriting(self):
        before = self.path.read_bytes()
        with env.registry_lock():
            with self.assertRaises(env.RegistryError) as failure:
                self.patch({'origin_state': 'LINKED_VERIFIED'})
        self.assertEqual(failure.exception.code, 'REGISTRY_LOCK_UNAVAILABLE')
        self.assertEqual(self.path.read_bytes(), before)

    def test_atomic_replace_failure_preserves_original_and_removes_temp(self):
        before = self.path.read_bytes()
        with mock.patch.object(env.os, 'replace', side_effect=OSError('synthetic')):
            with self.assertRaises(env.RegistryError) as failure:
                self.patch({'origin_state': 'LINKED_VERIFIED'})
        self.assertEqual(failure.exception.code, 'REGISTRY_ATOMIC_WRITE_FAILED')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_patch_cannot_own_task_history_or_unrelated_fields(self):
        with self.assertRaises(env.RegistryError) as failure:
            self.patch({'last_task_commit': 'must-not-overwrite'})
        self.assertEqual(failure.exception.code, 'REGISTRY_PATCH_FIELDS_INVALID')
        self.assertEqual(env.load()['projects'][0]['last_task_commit'], 'initial-task')

    def test_registry_write_failure_is_reported_safely_with_original_limit(self):
        self.path.write_text('{corrupted', encoding='utf-8')
        result = env.remote_block(self.stale, self.stale['projects'][0], 'GITHUB_RATE_LIMIT', 'lookup_repository')
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['code'], 'REGISTRY_UNREADABLE_OR_INVALID')
        self.assertEqual(result['cause_code'], 'GITHUB_RATE_LIMIT')
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{corrupted')


class LocalOriginTests(unittest.TestCase):
    def test_local_repository_status_and_pyw_scan_need_no_github_metadata(self):
        with tempfile.TemporaryDirectory(prefix='local-only-fixture-') as temp:
            root = Path(temp)
            subprocess.run(['git', '-C', str(root), 'init', '--initial-branch=main'], check=True, capture_output=True)
            (root / 'iniciar.pyw').write_text('value = 1\n', encoding='utf-8')
            (root / 'config.json').write_text('{}', encoding='utf-8')
            project = {'id': 'local-component', 'repo_root': str(root), 'remote': None}
            original_run = env.run
            def local_only(args, **kwargs):
                if str(args[0]) != 'git':
                    raise AssertionError('No real GitHub command permitted')
                return original_run(args, **kwargs)
            with mock.patch.object(env, 'run', side_effect=local_only):
                status = env.local_status(project)
                scan = env.scan_project(project)
            self.assertEqual(status['remote'], '')
            self.assertEqual(status['remote_state_recorded'], 'LOCAL_ONLY_NO_REMOTE')
            self.assertEqual(status['branch'], 'main')
            self.assertIn('iniciar.pyw', scan['approved_candidates'])
            self.assertTrue(any(row['path'] == 'config.json' for row in scan['deferred']))

    def test_real_git_link_is_local_and_preserves_existing_ssh_origin(self):
        with tempfile.TemporaryDirectory(prefix='origin-fixture-') as temp:
            root = Path(temp)
            subprocess.run(['git', '-C', str(root), 'init'], check=True, capture_output=True)
            project = {'id': 'fixture-project', 'repo_root': str(root), 'github_repo': REPO,
                       'remote': URL + '.git', 'remote_state': 'PENDING_PROVISIONING'}
            registry = {'github_owner': OWNER, 'projects': [project], 'publication_policy': copy.deepcopy(REMOTE_POLICY)}
            original_run = env.run
            def isolated_run(args, **kwargs):
                words = [str(x) for x in args]
                if words[0] == 'git':
                    return original_run(args, **kwargs)
                if words[:3] == [str(env.GH), 'api', 'user']:
                    return response(body={'login': OWNER})
                if words[:3] == [str(env.GH), 'api', 'repos/' + REPO]:
                    return response(body={'private': True, 'full_name': REPO, 'html_url': URL})
                raise AssertionError('No real GitHub command permitted')
            with mock.patch.object(env, 'run', side_effect=isolated_run), mock.patch.object(env, 'load', return_value=registry), mock.patch.object(env, 'save', side_effect=lambda reg, project, patch: dict(project, **patch)) as saved:
                self.assertEqual(env.ensure_remote(registry, project)['status'], 'VERIFIED')
                self.assertEqual(env.read_origin(root), URL + '.git')
                subprocess.run(['git', '-C', str(root), 'remote', 'set-url', 'origin', 'git@github.com:' + REPO + '.git'], check=True)
                self.assertEqual(env.ensure_remote(registry, project)['status'], 'VERIFIED')
                self.assertEqual(env.read_origin(root), 'git@github.com:' + REPO + '.git')
                self.assertEqual(saved.call_count, 2)
                subprocess.run(['git', '-C', str(root), 'remote', 'set-url', '--push', 'origin', 'https://github.com/other/repository.git'], check=True)
                self.assertEqual(env.ensure_remote(registry, project)['status'], 'BLOCKED')
                actual = subprocess.run(['git', '-C', str(root), 'remote', 'get-url', '--push', 'origin'], check=True, capture_output=True, text=True).stdout.strip()
                self.assertEqual(actual, 'https://github.com/other/repository.git')


class PublicEnsureRemoteTests(unittest.TestCase):
    fake_run = EnsureRemoteTests.fake_run
    creations = EnsureRemoteTests.creations
    links = EnsureRemoteTests.links

    def setUp(self):
        SelectedEnsureRemoteTests.setUp(self)
        self.project.update(classification='public_generic_distribution', visibility='public')
        self.selection['visibility'] = 'public'
        self.exception = {'project_id': self.project['id'], 'repository': REPO,
                          'source': 'DIRECT_USER_DECISION', 'scope': 'AUDITED_GENERIC_SKILLS_AGENTS',
                          'audited_tree': 'b' * 40, 'manifest_sha256': 'c' * 64}
        self.registry['publication_policy']['public_exceptions'] = [self.exception]
        # The actual immutable tree/manifest verifier is exercised with real Git
        # by PublicPublicationTests. Here failures and revocations discriminate
        # the helper's operation ordering without performing network requests.
        self.audit = mock.patch.object(env, 'verify_public_content').start()
        self.api_repos = [response(body={'private': False, 'full_name': REPO, 'html_url': URL})]

    def test_existing_audited_public_repository_is_verified_with_live_visibility(self):
        result = env.ensure_remote(self.registry, self.project)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertFalse(result['private'])
        self.assertEqual(self.project['remote_state'], 'PUBLIC_REPOSITORY_VERIFIED')
        self.assertFalse(self.creations())
        self.assertGreaterEqual(self.audit.call_count, 5)

    def test_public_creation_is_possible_only_for_selected_audited_exception(self):
        self.selection['create_remote'] = True
        self.api_repos.insert(0, response(404, {'message': 'Not Found'}))
        with mock.patch.dict(env.os.environ, {'GH_HOST': 'enterprise.invalid'}):
            result = env.ensure_remote(self.registry, self.project)
        self.assertEqual(result['status'], 'VERIFIED')
        creation = self.creations()[0]
        self.assertIn('--public', creation.args[0])
        self.assertNotIn('--private', creation.args[0])
        self.assertEqual(creation.kwargs['env']['GH_HOST'], 'github.com')

    def test_missing_or_other_repository_exception_never_calls_network_or_links(self):
        for exceptions in ([], [dict(self.exception, repository=OWNER + '/other')]):
            self.registry['publication_policy']['public_exceptions'] = exceptions
            self.assertEqual(env.ensure_remote(self.registry, self.project)['code'],
                             'PUBLICATION_PUBLIC_EXCEPTION_REQUIRED')
        self.run.assert_not_called()
        self.read_origin.assert_not_called()
        self.audit.assert_not_called()

    def test_invalid_audited_content_denies_before_local_or_remote_provisioning(self):
        self.audit.side_effect = env.PublicationPolicyError('PUBLICATION_MANIFEST_CONTENT_MISMATCH')
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'],
                         'PUBLICATION_MANIFEST_CONTENT_MISMATCH')
        self.run.assert_not_called()
        self.read_origin.assert_not_called()
        self.save.assert_not_called()

    def test_public_selection_does_not_link_private_or_missing_visibility_destination(self):
        for private in (True, None):
            self.api_repos = [response(body={'private': private, 'full_name': REPO, 'html_url': URL})]
            self.origins = [None]
            self.assertEqual(env.ensure_remote(self.registry, self.project)['code'], 'REPOSITORY_NOT_PUBLIC')
        self.assertFalse(self.links())
        self.assertFalse(self.creations())

    def test_revoked_public_exception_stops_after_account_check(self):
        original = self.fake_run
        def revoke(args, **kwargs):
            result = original(args, **kwargs)
            self.registry['publication_policy']['public_exceptions'] = []
            return result
        self.run.side_effect = revoke
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'],
                         'PUBLICATION_PUBLIC_EXCEPTION_REQUIRED')
        self.assertEqual(len(self.run.call_args_list), 1)
        self.assertFalse(self.creations())
        self.assertFalse(self.links())

    def test_visibility_change_before_creation_cannot_switch_the_requested_flag(self):
        self.selection['create_remote'] = True
        self.api_repos = [response(404, {'message': 'Not Found'})]
        original = self.fake_run
        def change_visibility(args, **kwargs):
            result = original(args, **kwargs)
            if [str(x) for x in args][1:3] == ['api', 'repos/' + REPO]:
                self.selection['visibility'] = 'private'
            return result
        self.run.side_effect = change_visibility
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'], 'PUBLICATION_VISIBILITY_CHANGED')
        self.assertFalse(self.creations())
        self.assertFalse(self.links())

    def test_public_content_is_rechecked_before_linking_after_remote_reads(self):
        original = self.fake_run
        def invalidate(args, **kwargs):
            result = original(args, **kwargs)
            if [str(x) for x in args][1:3] == ['api', 'repos/' + REPO]:
                self.audit.side_effect = env.PublicationPolicyError('PUBLICATION_AUDITED_TREE_MISMATCH')
            return result
        self.run.side_effect = invalidate
        self.assertEqual(env.ensure_remote(self.registry, self.project)['code'], 'PUBLICATION_AUDITED_TREE_MISMATCH')
        self.assertFalse(self.links())


if __name__ == '__main__':
    unittest.main(verbosity=2)
