"""Discriminating local-only tests. All Git mutations use disposable work/ repos."""
from pathlib import Path
import importlib.util
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

GUARD_PATH = Path(__file__).resolve().parents[1] / 'scripts/guard.py'
SPEC = importlib.util.spec_from_file_location('publication_guard', GUARD_PATH)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
ZERO = '0' * 40
FAKE_SECRET = 'dapi' + 'a' * 32


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='guard-fixture-', dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        # CLI tests carry an isolated portable policy map; never read user state.
        runtime = self.root / '.guard-runtime'
        (runtime / 'scripts').mkdir(parents=True)
        (runtime / 'references').mkdir()
        self.cli_script = runtime / 'scripts/guard.py'
        self.cli_script.write_bytes(GUARD_PATH.read_bytes())
        self.policy_file = runtime / 'references/ambiente-repos.local.json'
        self.policy_map = {'projects': [], 'publication_policy': {
            'mode': 'LOCAL_ONLY', 'source': 'DIRECT_USER_DECISION', 'as_of': '2026-10-29',
            'create_remote': False, 'push': False}}
        self.policy_file.write_text(json.dumps(self.policy_map), encoding='utf-8')
        self.hooks = self.root / 'empty-hooks'
        self.hooks.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Guard synthetic fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')

    def git(self, *args, input=None):
        return subprocess.run(['git', '-c', 'core.hooksPath=' + str(self.hooks),
                               '-C', str(self.root), *args], input=input,
                              capture_output=True, check=True).stdout

    def put(self, name, data):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode() if isinstance(data, str) else data)
        # Deliberately stage rejected fixtures even with the user's global ignore.
        self.git('add', '-f', '--', name)

    def commit(self, message='synthetic fixture'):
        self.git('commit', '-m', message)
        return self.git('rev-parse', 'HEAD').decode().strip()

    def update(self, local, remote=ZERO, name='main'):
        return f'refs/heads/{name} {local} refs/heads/{name} {remote}\n'

    def labels(self, findings):
        return {issue for item in findings for issue in item['issues']}

    def cli(self, updates=None, root=None):
        args = [sys.executable, str(self.cli_script), '--root', str(root or self.root), '--json']
        if updates is not None:
            args.append('--pre-push')
        return subprocess.run(args, input=updates, capture_output=True, text=True)

    def test_clean_code_is_allowed(self):
        self.put('src/task.py', 'def answer():\n    return 42\n')
        self.assertEqual(guard.inspect_index(self.root), [])
        head = self.commit()
        self.assertEqual(guard.inspect_push(self.root, self.update(head)), [])

    def test_staged_secret_is_blocked_even_with_clean_worktree(self):
        self.put('src/task.py', 'value = "' + FAKE_SECRET + '"\n')
        (self.root / 'src/task.py').write_text('value = None\n')
        self.assertIn('databricks_token', self.labels(guard.inspect_index(self.root)))

    def test_unstaged_secret_does_not_replace_clean_index(self):
        self.put('src/task.py', 'value = None\n')
        (self.root / 'src/task.py').write_text('value = "' + FAKE_SECRET + '"\n')
        self.assertEqual(guard.inspect_index(self.root), [])

    def test_data_and_private_directories_block(self):
        self.put('samples.csv', 'synthetic,value\na,1\n')
        self.put('outputs/generated.py', 'value = 1\n')
        self.put('config.local.json', '{}')
        labels = self.labels(guard.inspect_index(self.root))
        self.assertTrue({'data_or_document_requires_separate_policy',
                         'generated_or_private_directory',
                         'credential_or_local_configuration_path'}.issubset(labels))

    def test_notebook_output_blocked_and_empty_notebook_allowed(self):
        clean = json.dumps({'cells': [{'cell_type': 'code', 'source': ['x=1'],
                                      'outputs': [], 'execution_count': None}]})
        self.put('clean.ipynb', clean)
        self.assertEqual(guard.inspect_index(self.root), [])
        obj = json.loads(clean)
        obj['cells'][0]['outputs'] = [{'output_type': 'stream', 'text': ['synthetic']}]
        self.put('clean.ipynb', json.dumps(obj))
        self.assertIn('notebook_contains_outputs_or_execution_state',
                      self.labels(guard.inspect_index(self.root)))

    def test_invalid_notebook_shape_fails_closed(self):
        for data in (b'[]', b'{}', b'{"cells":[null]}', b'{'):
            with self.subTest(data=data):
                self.assertIn('invalid_notebook_json', guard.inspect_content('task.ipynb', data))

    def test_staged_symlink_mode_blocked_without_worktree_symlink(self):
        self.put('link.py', 'ordinary = 1\n')
        oid = self.git('hash-object', '-w', '--stdin', input=b'elsewhere.py').decode().strip()
        self.git('update-index', '--cacheinfo', f'120000,{oid},link.py')
        self.assertFalse((self.root / 'link.py').is_symlink())
        self.assertIn('symlink_requires_review', self.labels(guard.inspect_index(self.root)))

    def test_gitlink_blocked(self):
        self.put('safe.py', 'value = 1\n')
        head = self.commit()
        self.git('update-index', '--add', '--cacheinfo', f'160000,{head},component')
        self.assertIn('gitlink_requires_separate_review', self.labels(guard.inspect_index(self.root)))

    def test_type_change_from_link_to_secret_file_is_blocked(self):
        self.put('link.py', 'ordinary = 1\n')
        oid = self.git('hash-object', '-w', '--stdin', input=b'elsewhere.py').decode().strip()
        self.git('update-index', '--cacheinfo', f'120000,{oid},link.py')
        self.commit()
        self.put('link.py', 'value = "' + FAKE_SECRET + '"\n')
        # Windows core.symlinks=false can preserve the old mode during add.
        oid = self.git('hash-object', '-w', '--', 'link.py').decode().strip()
        self.git('update-index', '--cacheinfo', f'100644,{oid},link.py')
        self.assertEqual(self.git('diff', '--cached', '--name-status').decode().split()[0], 'T')
        self.assertIn('databricks_token', self.labels(guard.inspect_index(self.root)))

    def test_env_example_placeholders_allowed_but_secrets_blocked(self):
        self.put('.env.example', 'DATABRICKS_TOKEN=<set-locally>\n')
        self.assertEqual(guard.inspect_index(self.root), [])
        self.put('.env.example', 'DATABRICKS_TOKEN=' + FAKE_SECRET + '\n')
        self.assertIn('databricks_token', self.labels(guard.inspect_index(self.root)))
        self.assertIn('credential_or_local_configuration_path',
                      guard.inspect_content('.env.production.example', b'DATABRICKS_TOKEN=<set-locally>'))

    def test_push_secret_blocked_even_when_index_is_clean(self):
        self.put('task.py', 'value = "' + FAKE_SECRET + '"\n')
        head = self.commit()
        self.assertEqual(guard.inspect_index(self.root), [])
        self.assertIn('databricks_token', self.labels(guard.inspect_push(self.root, self.update(head))))

    def test_push_includes_intermediate_commits_even_if_head_is_clean(self):
        self.put('task.py', 'value = 1\n')
        base = self.commit()
        self.put('task.py', 'value = "' + FAKE_SECRET + '"\n')
        bad = self.commit()
        self.put('task.py', 'value = 2\n')
        head = self.commit()
        findings = guard.inspect_push(self.root, self.update(head, base))
        self.assertTrue(any(f.get('commit') == bad and 'databricks_token' in f['issues']
                            for f in findings))

    def test_push_checks_supplied_ref_instead_of_head_or_index(self):
        self.put('task.py', 'value = 1\n')
        base = self.commit()
        self.put('task.py', 'value = "' + FAKE_SECRET + '"\n')
        bad = self.commit()
        self.git('checkout', '--detach', base)
        self.assertEqual(guard.inspect_index(self.root), [])
        self.assertIn('databricks_token', self.labels(guard.inspect_push(self.root, self.update(bad, base))))

    def test_push_clean_existing_update_excludes_old_history(self):
        self.put('removed.py', 'value = "' + FAKE_SECRET + '"\n')
        base = self.commit()
        self.git('rm', '--', 'removed.py')
        self.put('safe.py', 'value = 1\n')
        head = self.commit()
        self.assertEqual(guard.inspect_push(self.root, self.update(head, base)), [])

    def test_push_multiple_refs_and_deletion(self):
        self.put('task.py', 'value = 1\n')
        base = self.commit()
        self.put('task.py', 'value = "' + FAKE_SECRET + '"\n')
        bad = self.commit()
        updates = self.update(ZERO, base, 'deleted') + self.update(base, base) + self.update(bad, base, 'other')
        self.assertIn('databricks_token', self.labels(guard.inspect_push(self.root, updates)))
        self.assertEqual(guard.inspect_push(self.root, self.update(ZERO, bad)), [])

    def test_commit_metadata_is_inspected_without_leaking(self):
        self.put('task.py', 'value = 1\n')
        head = self.commit('synthetic ' + FAKE_SECRET)
        result = self.cli(self.update(head))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(FAKE_SECRET, result.stdout + result.stderr)
        self.assertIn('(commit metadata)', result.stdout)

    def test_annotated_tag_metadata_is_inspected(self):
        self.put('task.py', 'value = 1\n')
        self.commit()
        self.git('tag', '-a', 'fixture', '-m', 'synthetic ' + FAKE_SECRET)
        tag = self.git('rev-parse', 'refs/tags/fixture').decode().strip()
        self.assertIn('databricks_token', self.labels(guard.inspect_push(self.root, self.update(tag))))

    def test_unknown_old_sha_and_invalid_input_fail_closed_without_output(self):
        self.put('task.py', 'value = 1\n')
        head = self.commit()
        for updates in (self.update(head, 'f' * 40), 'bad input\n'):
            with self.subTest(updates=updates):
                result = self.cli(updates)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn('fatal:', result.stderr)
                self.assertNotIn(updates.strip(), result.stdout + result.stderr)

    def test_binary_and_large_files_require_review(self):
        self.assertIn('binary_or_non_utf8_requires_review', guard.inspect_content('asset.bin', b'\xff'))
        self.put('large.py', b'x' * (guard.REVIEW_LIMIT + 1))
        self.assertIn('file_exceeds_2MB_review_limit', self.labels(guard.inspect_index(self.root)))

    def test_empty_push_updates_are_valid_noop(self):
        self.assertEqual(guard.inspect_push(self.root, ''), [])

    def test_batch_132_blobs_uses_four_git_processes(self):
        source = self.root / 'src'
        source.mkdir()
        for index in range(132):
            (source / f'task_{index:03}.py').write_text(f'value = {index}\n')
        self.git('add', '-f', '--', 'src')
        started = time.perf_counter()
        with mock.patch.object(guard, 'git', wraps=guard.git) as calls:
            self.assertEqual(guard.inspect_index(self.root), [])
        elapsed = time.perf_counter() - started
        commands = [call.args[1:] for call in calls.call_args_list]
        self.assertEqual(len(commands), 4)
        self.assertEqual(sum(args[:2] == ('cat-file', '--batch-check') for args in commands), 1)
        self.assertEqual(sum(args[:2] == ('cat-file', '--batch') for args in commands), 1)
        print(f'132 unique blobs: {len(commands)} Git processes; {elapsed:.3f}s')
        head = self.commit()
        started = time.perf_counter()
        with mock.patch.object(guard, 'git', wraps=guard.git) as calls:
            self.assertEqual(guard.inspect_push(self.root, self.update(head)), [])
        elapsed = time.perf_counter() - started
        commands = [call.args[1:] for call in calls.call_args_list]
        self.assertLessEqual(len(commands), 7)
        self.assertEqual(sum(args[:2] == ('cat-file', '--batch-check') for args in commands), 1)
        self.assertEqual(sum(args[:2] == ('cat-file', '--batch') for args in commands), 1)
        print(f'132 unique blobs, one commit push: {len(commands)} Git processes; {elapsed:.3f}s')

    def test_batch_reuses_oid_but_preserves_path_policy(self):
        self.put('safe.py', 'value = 1\n')
        self.put('outputs/safe.py', 'value = 1\n')
        with mock.patch.object(guard, 'git', wraps=guard.git) as calls:
            findings = guard.inspect_index(self.root)
        self.assertEqual(findings, [{'path': 'outputs/safe.py', 'issues': ['generated_or_private_directory']}])
        batches = [call for call in calls.call_args_list if call.args[1:] == ('cat-file', '--batch')]
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0].kwargs['input'].splitlines()), 1)

    def test_content_batches_are_bounded_and_parsed_by_size(self):
        for index in range(3):
            self.put(f'task_{index}.py', f'# {index}\n# fake header: abcd blob 12\nvalue = 1\n')
        with mock.patch.object(guard, 'BATCH_BYTES', 220), mock.patch.object(guard, 'git', wraps=guard.git) as calls:
            self.assertEqual(guard.inspect_index(self.root), [])
        batches = [call for call in calls.call_args_list if call.args[1:] == ('cat-file', '--batch')]
        self.assertEqual(len(batches), 3)

    def test_large_blob_is_not_read_by_content_batch(self):
        self.put('large.py', b'x' * (guard.REVIEW_LIMIT + 1))
        with mock.patch.object(guard, 'git', wraps=guard.git) as calls:
            self.assertIn('file_exceeds_2MB_review_limit', self.labels(guard.inspect_index(self.root)))
        self.assertFalse(any(call.args[1:] == ('cat-file', '--batch') for call in calls.call_args_list))

    def test_incomplete_batch_content_fails_closed(self):
        oid = 'a' * 40
        responses = [(oid + ' blob 10\n').encode(), (oid + ' blob 10\nshort').encode()]
        with mock.patch.object(guard, 'git', side_effect=responses):
            with self.assertRaises(ValueError):
                guard.inspect_entries(self.root, [('safe.py', '100644', oid)])

    def register_local_only(self, root=None):
        self.policy_map['projects'] = [{'id': 'synthetic-project', 'repo_root': str(root or self.root)}]
        self.policy_file.write_text(json.dumps(self.policy_map), encoding='utf-8')

    def test_local_only_blocks_push_before_content_without_exposing_input(self):
        self.register_local_only()
        result = self.cli('invalid input containing ' + FAKE_SECRET)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report['publication_policy']['code'], 'PUBLICATION_LOCAL_ONLY')
        self.assertIn('exact registered', report['scope'])
        self.assertNotIn(FAKE_SECRET, result.stdout + result.stderr)

    def test_local_only_allows_clean_local_commit(self):
        self.register_local_only()
        self.put('safe.py', 'value = 1\n')
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(len(self.commit()), 40)

    def test_subdirectory_cannot_evade_registered_git_root(self):
        self.register_local_only()
        subdirectory = self.root / 'subdirectory'
        subdirectory.mkdir()
        result = self.cli('', root=subdirectory)
        self.assertEqual(result.returncode, 1)
        self.assertIn('PUBLICATION_LOCAL_ONLY', result.stdout)

    def test_codex_parent_prefix_does_not_block_unregistered_temporary_repo(self):
        self.register_local_only(Path(__file__).resolve().parents[3])
        self.assertEqual(self.cli('').returncode, 0)

    def test_absent_corrupt_or_missing_policy_blocks_push_but_not_commit(self):
        self.put('safe.py', 'value = 1\n')
        for contents in (None, '{corrupt', json.dumps({'projects': []})):
            with self.subTest(contents=contents):
                if contents is None:
                    self.policy_file.unlink(missing_ok=True)
                else:
                    self.policy_file.write_text(contents, encoding='utf-8')
                self.assertEqual(self.cli('').returncode, 2)
                self.assertEqual(self.cli().returncode, 0)

    def test_inconsistent_local_only_policy_is_not_remote_permission(self):
        self.policy_map['publication_policy']['push'] = True
        self.policy_file.write_text(json.dumps(self.policy_map), encoding='utf-8')
        result = self.cli('')
        self.assertEqual(result.returncode, 2)
        self.assertIn('PUBLICATION_POLICY_INVALID', result.stdout)
        self.policy_map['publication_policy']['push'] = False
        self.policy_map['projects'] = [{'id': 'relative-path', 'repo_root': 'relative-directory'}]
        self.policy_file.write_text(json.dumps(self.policy_map), encoding='utf-8')
        result = self.cli('')
        self.assertEqual(result.returncode, 2)
        self.assertIn('PUBLICATION_REGISTRY_INVALID', result.stdout)


class PywSourceTests(unittest.TestCase):
    def test_pyw_sources_receive_python_syntax_validation(self):
        with tempfile.TemporaryDirectory(prefix='source-pyw-check-') as folder:
            root = Path(folder).resolve()
            (root / 'good.pyw').write_text('print("ready")\n', encoding='utf-8')
            (root / 'bad.pyw').write_text('def broken(:\n', encoding='utf-8')
            found = {item['path']: item['issues'] for item in guard.check_sources(root, ['good.pyw', 'bad.pyw'])}
            self.assertEqual(found['good.pyw'], [])
            self.assertIn('python_parse_failed', found['bad.pyw'])


class SelectedPublicationTests(unittest.TestCase):
    setUp = GuardTests.setUp
    git = GuardTests.git
    put = GuardTests.put
    commit = GuardTests.commit
    update = GuardTests.update

    def select(self, head, old=ZERO):
        self.repository = 'fixture-owner/fixture-project'
        self.url = 'https://github.com/' + self.repository + '.git'
        self.project = {'id': 'fixture-project', 'repo_root': str(self.root), 'github_repo': self.repository}
        self.selection = {'id': 'fixture-selection', 'project_id': self.project['id'],
                          'repository': self.repository, 'visibility': 'private', 'create_remote': False,
                          'update': {'local_sha': head, 'remote_ref': 'refs/heads/main', 'expected_remote_sha': old}}
        self.policy_map.update(github_owner='fixture-owner', projects=[self.project])
        self.policy_map['publication_policy'].update(mode='PRIVATE_SELECTED', selections=[self.selection])
        self.save_policy()

    def save_policy(self):
        self.policy_file.write_text(json.dumps(self.policy_map), encoding='utf-8')

    def clean_selection(self, old=ZERO):
        self.put('src/tool.py', 'value = 1\n')
        head = self.commit()
        self.select(head, old)
        return head

    def denial(self, updates, url=None, root=None):
        with mock.patch.object(guard, 'REGISTRY', self.policy_file):
            return guard.push_policy_denial(root or self.root, updates, url or self.url)

    def test_exact_selection_allows_only_after_live_private_verification(self):
        head = self.clean_selection()
        with mock.patch.object(guard, 'private_destination_denial', return_value=None) as private:
            self.assertIsNone(self.denial(self.update(head)))
        private.assert_called_once_with(self.repository)

    def test_unknown_root_and_unselected_project_block_before_network(self):
        head = self.clean_selection()
        with mock.patch.object(guard, 'private_destination_denial') as private:
            self.assertEqual(self.denial(self.update(head), root=self.root / 'unknown')['code'], 'PUBLICATION_NOT_SELECTED')
            self.policy_map['publication_policy']['selections'] = []
            self.save_policy()
            self.assertEqual(self.denial(self.update(head))['code'], 'PUBLICATION_NOT_SELECTED')
        private.assert_not_called()

    def test_sha_ref_old_state_and_destination_are_all_binding(self):
        head = self.clean_selection()
        cases = [(self.update('a' * 40), self.url), (self.update(head, name='other'), self.url),
                 (self.update(head, remote='b' * 40), self.url),
                 (self.update(head), 'https://github.com/fixture-owner/other.git'),
                 (self.update(head), 'https://credential@github.com/' + self.repository + '.git')]
        with mock.patch.object(guard, 'private_destination_denial') as private:
            for update, url in cases:
                with self.subTest(update=update, url=url):
                    self.assertEqual(self.denial(update, url)['code'], 'PUBLICATION_UPDATE_NOT_SELECTED')
        private.assert_not_called()

    def test_multiple_updates_deletion_and_tag_destination_are_rejected(self):
        head = self.clean_selection()
        updates = [self.update(head) * 2, self.update(ZERO, remote=head),
                   self.update(head).replace('refs/heads/main', 'refs/tags/v1')]
        with mock.patch.object(guard, 'private_destination_denial') as private:
            for update in updates:
                self.assertEqual(self.denial(update)['code'], 'PUBLICATION_UPDATE_NOT_SELECTED')
        private.assert_not_called()

    def test_non_fast_forward_is_rejected_before_network(self):
        first = self.clean_selection()
        self.put('src/tool.py', 'value = 2\n')
        second = self.commit()
        self.select(first, second)
        with mock.patch.object(guard, 'private_destination_denial') as private:
            self.assertEqual(self.denial(self.update(first, second))['code'], 'PUBLICATION_NON_FAST_FORWARD')
        private.assert_not_called()

    def test_fast_forward_selection_is_accepted(self):
        first = self.clean_selection()
        self.put('src/tool.py', 'value = 2\n')
        second = self.commit()
        self.select(second, first)
        with mock.patch.object(guard, 'private_destination_denial', return_value=None):
            self.assertIsNone(self.denial(self.update(second, first)))

    def test_malformed_or_duplicate_grants_never_authorize(self):
        self.clean_selection()
        mutations = [lambda p: p['selections'].append(copy.deepcopy(p['selections'][0])),
                     lambda p: p['selections'][0].update(visibility='public'),
                     lambda p: p['selections'][0].update(repository='other-owner/repository'),
                     lambda p: p['selections'][0]['update'].update(local_sha='main'),
                     lambda p: p['selections'][0]['update'].update(remote_ref='refs/heads/../main'),
                     lambda p: p['selections'][0]['update'].update(remote_ref='refs/tags/v1'),
                     lambda p: p.update(push=True), lambda p: p.pop('selections')]
        for mutate in mutations:
            with self.subTest(mutation=str(mutate)):
                registry = copy.deepcopy(self.policy_map)
                mutate(registry['publication_policy'])
                with self.assertRaises(guard.PublicationPolicyError):
                    guard.publication_policy(registry)

    def test_duplicate_registered_roots_are_not_ambiguous_permission(self):
        head = self.clean_selection()
        self.policy_map['projects'].append(dict(self.project, id='different-project'))
        self.save_policy()
        with mock.patch.object(guard, 'private_destination_denial') as private:
            self.assertEqual(self.denial(self.update(head))['code'], 'PUBLICATION_REGISTRY_INVALID')
        private.assert_not_called()

    def run_main(self, updates):
        with mock.patch.object(guard, 'REGISTRY', self.policy_file), \
             mock.patch.object(sys, 'argv', ['guard.py', '--root', str(self.root), '--pre-push',
                                           '--remote-name=origin', '--remote-url=' + self.url, '--json']), \
             mock.patch.object(sys.stdin, 'read', return_value=updates), \
             mock.patch('builtins.print') as printed:
            code = guard.main()
        return code, printed

    def test_selected_push_still_blocks_secret_in_intermediate_commit(self):
        self.put('src/tool.py', 'value = "' + FAKE_SECRET + '"\n')
        self.commit()
        self.put('src/tool.py', 'value = None\n')
        head = self.commit()
        self.select(head)
        with mock.patch.object(guard, 'private_destination_denial', return_value=None):
            code, printed = self.run_main(self.update(head))
        self.assertEqual(code, 1)
        output = printed.call_args.args[0]
        self.assertIn('databricks_token', output)
        self.assertNotIn(FAKE_SECRET, output)

    def test_revocation_during_content_review_stops_main(self):
        head = self.clean_selection()
        original = guard.inspect_push
        def revoke(root, updates):
            findings = original(root, updates)
            self.policy_map['publication_policy']['selections'] = []
            self.save_policy()
            return findings
        with mock.patch.object(guard, 'private_destination_denial', return_value=None), \
             mock.patch.object(guard, 'inspect_push', side_effect=revoke):
            code, printed = self.run_main(self.update(head))
        self.assertEqual(code, 1)
        self.assertIn('PUBLICATION_NOT_SELECTED', printed.call_args.args[0])

    def test_selected_clean_main_checks_destination_and_content(self):
        head = self.clean_selection()
        with mock.patch.object(guard, 'private_destination_denial', return_value=None) as private:
            code, printed = self.run_main(self.update(head))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(printed.call_args.args[0])['status'], 'PASS')
        private.assert_called_once_with(self.repository)


class PrivateDestinationTests(unittest.TestCase):
    repository = 'fixture-owner/fixture-project'

    def response(self, body, code=0):
        return subprocess.CompletedProcess([], code, json.dumps(body), 'private-response-never-echoed')

    def test_explicit_github_host_wins_over_alternative_environment(self):
        payload = {'private': True, 'full_name': self.repository, 'html_url': 'https://github.com/' + self.repository}
        with mock.patch.dict(guard.os.environ, {'GH_HOST': 'enterprise.invalid'}), \
             mock.patch.object(guard.subprocess, 'run', side_effect=[self.response({'login': 'fixture-owner'}), self.response(payload)]) as run:
            self.assertIsNone(guard.private_destination_denial(self.repository))
        for call in run.call_args_list:
            self.assertEqual(call.args[0][-2:], ['--hostname', 'github.com'])

    def test_public_missing_wrong_identity_and_wrong_owner_block(self):
        valid = {'private': True, 'full_name': self.repository, 'html_url': 'https://github.com/' + self.repository}
        cases = [({'login': 'fixture-owner'}, dict(valid, private=False), 'REPOSITORY_NOT_PRIVATE'),
                 ({'login': 'fixture-owner'}, {}, 'REPOSITORY_NOT_PRIVATE'),
                 ({'login': 'different'}, valid, 'AUTHENTICATED_OWNER_MISMATCH'),
                 ({'login': 'fixture-owner'}, dict(valid, full_name='fixture-owner/other'), 'REPOSITORY_IDENTITY_MISMATCH'),
                 ({'login': 'fixture-owner'}, dict(valid, html_url='https://enterprise.invalid/' + self.repository), 'REPOSITORY_IDENTITY_MISMATCH')]
        for user, repo, expected in cases:
            with self.subTest(expected=expected), mock.patch.object(guard.subprocess, 'run', side_effect=[self.response(user), self.response(repo)]):
                self.assertEqual(guard.private_destination_denial(self.repository), expected)

    def test_auth_permission_rate_transport_and_invalid_response_fail_closed(self):
        cases = [self.response({'message': 'Bad credentials'}, 1), self.response({'message': 'Forbidden'}, 1),
                 self.response({'message': 'rate limit'}, 1), subprocess.CompletedProcess([], 0, 'invalid-json', ''),
                 self.response([])]
        for response in cases:
            with self.subTest(response=response), mock.patch.object(guard.subprocess, 'run', return_value=response):
                self.assertEqual(guard.private_destination_denial(self.repository), 'PUBLICATION_DESTINATION_UNVERIFIABLE')
        with mock.patch.object(guard.subprocess, 'run', side_effect=subprocess.TimeoutExpired('redacted', 30)):
            self.assertEqual(guard.private_destination_denial(self.repository), 'PUBLICATION_DESTINATION_UNVERIFIABLE')


class PublicPublicationTests(unittest.TestCase):
    setUp = GuardTests.setUp
    git = GuardTests.git
    put = GuardTests.put
    commit = GuardTests.commit
    update = GuardTests.update
    select = SelectedPublicationTests.select
    save_policy = SelectedPublicationTests.save_policy
    denial = SelectedPublicationTests.denial
    run_main = SelectedPublicationTests.run_main

    def prepare(self, manifest=None):
        self.put('src/tool.py', 'value = 1\n')
        if manifest is None:
            manifest = {'schema_version': 1, 'files': [
                {'path': 'src/tool.py', 'sha256': hashlib.sha256(b'value = 1\n').hexdigest()}]}
        self.put('PUBLICATION_MANIFEST.json', json.dumps(manifest))
        head = self.commit()
        self.select(head)
        self.project['classification'] = 'public_generic_distribution'
        self.selection['visibility'] = 'public'
        self.exception = {'project_id': self.project['id'], 'repository': self.repository,
                          'source': 'DIRECT_USER_DECISION', 'scope': 'AUDITED_GENERIC_SKILLS_AGENTS',
                          'audited_tree': self.git('rev-parse', head + '^{tree}').decode().strip(),
                          'manifest_sha256': hashlib.sha256((self.root / 'PUBLICATION_MANIFEST.json').read_bytes()).hexdigest()}
        self.policy_map['publication_policy']['public_exceptions'] = [self.exception]
        self.save_policy()
        return head

    def test_exact_audited_public_selection_checks_public_destination(self):
        head = self.prepare()
        with mock.patch.object(guard, 'destination_denial', return_value=None) as destination:
            self.assertIsNone(self.denial(self.update(head)))
        destination.assert_called_once_with(self.repository, 'public')

    def test_missing_other_project_or_other_repository_exception_denies_before_network(self):
        head = self.prepare()
        original = copy.deepcopy(self.policy_map)
        mutations = [lambda p: p.update(public_exceptions=[]),
                     lambda p: p['public_exceptions'][0].update(project_id='another-project'),
                     lambda p: p['public_exceptions'][0].update(repository='fixture-owner/another-project')]
        with mock.patch.object(guard, 'destination_denial') as destination:
            for mutate in mutations:
                self.policy_map = copy.deepcopy(original)
                mutate(self.policy_map['publication_policy'])
                self.save_policy()
                self.assertEqual(self.denial(self.update(head))['code'], 'PUBLICATION_PUBLIC_EXCEPTION_REQUIRED')
        destination.assert_not_called()

    def test_public_exception_does_not_authorize_private_component_or_unknown_root(self):
        head = self.prepare()
        with mock.patch.object(guard, 'destination_denial') as destination:
            self.project['classification'] = 'corporate_component'
            self.save_policy()
            self.assertEqual(self.denial(self.update(head))['code'], 'PUBLICATION_PUBLIC_EXCEPTION_REQUIRED')
            self.project['classification'] = 'public_generic_distribution'
            self.save_policy()
            self.assertEqual(self.denial(self.update(head), root=self.root / 'another')['code'], 'PUBLICATION_NOT_SELECTED')
        destination.assert_not_called()

    def test_multiple_malformed_or_unapproved_exceptions_never_authorize(self):
        self.prepare()
        mutations = [lambda p: p['public_exceptions'].append(copy.deepcopy(p['public_exceptions'][0])),
                     lambda p: p['public_exceptions'][0].update(source='INFERRED'),
                     lambda p: p['public_exceptions'][0].update(scope='ALL_PROJECTS'),
                     lambda p: p['public_exceptions'][0].update(audited_tree='main'),
                     lambda p: p['public_exceptions'][0].update(manifest_sha256='missing'),
                     lambda p: p.update(mode='PRIVATE_REMOTE_ALLOWED', selections=[])]
        for mutate in mutations:
            registry = copy.deepcopy(self.policy_map)
            mutate(registry['publication_policy'])
            with self.assertRaises(guard.PublicationPolicyError) as failure:
                guard.publication_policy(registry)
            self.assertEqual(failure.exception.code, 'PUBLICATION_PUBLIC_EXCEPTION_INVALID')

    def test_changed_tree_and_manifest_blob_hash_deny_before_network(self):
        head = self.prepare()
        original = copy.deepcopy(self.exception)
        with mock.patch.object(guard, 'destination_denial') as destination:
            for key, value, code in [('audited_tree', 'a' * 40, 'PUBLICATION_AUDITED_TREE_MISMATCH'),
                                     ('manifest_sha256', 'b' * 64, 'PUBLICATION_MANIFEST_HASH_MISMATCH')]:
                self.exception.clear(); self.exception.update(original); self.exception[key] = value
                self.save_policy()
                self.assertEqual(self.denial(self.update(head))['code'], code)
        destination.assert_not_called()

    def test_manifest_content_digest_and_exact_tree_closure_are_required(self):
        cases = [({'schema_version': 1, 'files': [{'path': 'src/tool.py', 'sha256': '0' * 64}]},
                  'PUBLICATION_MANIFEST_CONTENT_MISMATCH'),
                 ({'schema_version': 1, 'files': []}, 'PUBLICATION_MANIFEST_TREE_MISMATCH'),
                 ({'schema_version': 1, 'files': [{'path': 'missing.py', 'sha256': '0' * 64}]},
                  'PUBLICATION_MANIFEST_TREE_MISMATCH')]
        with mock.patch.object(guard, 'destination_denial') as destination:
            for manifest, code in cases:
                head = self.prepare(manifest)
                self.assertEqual(self.denial(self.update(head))['code'], code)
        destination.assert_not_called()

    def test_manifest_rejects_self_traversal_duplicate_paths_and_unknown_fields(self):
        base = {'path': 'src/tool.py', 'sha256': hashlib.sha256(b'value = 1\n').hexdigest()}
        cases = [{'schema_version': 1, 'files': [base, base]},
                 {'schema_version': 1, 'files': [dict(base, path='../src/tool.py')]},
                 {'schema_version': 1, 'files': [dict(base, path='PUBLICATION_MANIFEST.json')]},
                 {'schema_version': True, 'files': [base]},
                 {'schema_version': 1, 'files': [base], 'private_metadata': 'not-allowed'}]
        with mock.patch.object(guard, 'destination_denial') as destination:
            for manifest in cases:
                head = self.prepare(manifest)
                self.assertEqual(self.denial(self.update(head))['code'], 'PUBLICATION_MANIFEST_INVALID')
        destination.assert_not_called()

    def test_manifest_duplicate_json_keys_are_rejected_even_with_approved_hash(self):
        self.prepare()
        self.put('PUBLICATION_MANIFEST.json', '{"schema_version":1,"schema_version":1,"files":[]}')
        head = self.commit()
        self.selection['update']['local_sha'] = head
        self.exception['audited_tree'] = self.git('rev-parse', head + '^{tree}').decode().strip()
        self.exception['manifest_sha256'] = hashlib.sha256((self.root / 'PUBLICATION_MANIFEST.json').read_bytes()).hexdigest()
        self.save_policy()
        with mock.patch.object(guard, 'destination_denial') as destination:
            self.assertEqual(self.denial(self.update(head))['code'], 'PUBLICATION_PUBLIC_CONTENT_UNVERIFIABLE')
        destination.assert_not_called()

    def test_public_tree_rejects_symlink_and_gitlink_modes(self):
        first = self.prepare()
        for mode, target in [('120000', self.git('hash-object', '-w', '--stdin', input=b'outside').decode().strip()),
                             ('160000', first)]:
            self.git('update-index', '--add', '--cacheinfo', f'{mode},{target},component')
            head = self.commit()
            self.selection['update']['local_sha'] = head
            self.exception['audited_tree'] = self.git('rev-parse', head + '^{tree}').decode().strip()
            self.save_policy()
            with mock.patch.object(guard, 'destination_denial') as destination:
                self.assertEqual(self.denial(self.update(head))['code'], 'PUBLICATION_PUBLIC_TREE_MODE_INVALID')
            destination.assert_not_called()

    def test_public_main_rechecks_revocation_after_content_review(self):
        head = self.prepare()
        original = guard.inspect_push
        def revoke(root, updates):
            findings = original(root, updates)
            self.policy_map['publication_policy']['public_exceptions'] = []
            self.save_policy()
            return findings
        with mock.patch.object(guard, 'destination_denial', return_value=None), \
             mock.patch.object(guard, 'inspect_push', side_effect=revoke):
            code, printed = self.run_main(self.update(head))
        self.assertEqual(code, 1)
        self.assertIn('PUBLICATION_PUBLIC_EXCEPTION_REQUIRED', printed.call_args.args[0])

    def test_public_main_checks_immutable_manifest_again_after_content_review(self):
        head = self.prepare()
        with mock.patch.object(guard, 'destination_denial', return_value=None), \
             mock.patch.object(guard, 'verify_public_content', wraps=guard.verify_public_content) as content:
            code, printed = self.run_main(self.update(head))
        self.assertEqual(code, 0)
        self.assertEqual(content.call_count, 2)
        self.assertEqual(json.loads(printed.call_args.args[0])['status'], 'PASS')

    def test_public_clean_tip_does_not_hide_sensitive_intermediate_history(self):
        self.put('removed.py', 'value = "' + FAKE_SECRET + '"\n')
        self.commit()
        self.git('rm', '--', 'removed.py')
        head = self.prepare()
        with mock.patch.object(guard, 'destination_denial', return_value=None):
            code, printed = self.run_main(self.update(head))
        self.assertEqual(code, 1)
        output = printed.call_args.args[0]
        self.assertIn('databricks_token', output)
        self.assertNotIn(FAKE_SECRET, output)

    def test_destination_visibility_is_exact_for_both_private_and_public(self):
        repository = 'fixture-owner/fixture-project'
        valid = {'full_name': repository, 'html_url': 'https://github.com/' + repository}
        def response(body):
            return subprocess.CompletedProcess([], 0, json.dumps(body), '')
        for visibility, is_private, expected in [('public', False, None),
                                                 ('public', True, 'REPOSITORY_NOT_PUBLIC'),
                                                 ('public', None, 'REPOSITORY_NOT_PUBLIC'),
                                                 ('private', False, 'REPOSITORY_NOT_PRIVATE')]:
            with mock.patch.object(guard.subprocess, 'run', side_effect=[
                    response({'login': 'fixture-owner'}), response(dict(valid, private=is_private))]):
                self.assertEqual(guard.destination_denial(repository, visibility), expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
