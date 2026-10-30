import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/validate_distribution.py'
spec = importlib.util.spec_from_file_location('validator', SOURCE)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.files = {'README.md': b'[License](LICENSE)\n', 'LICENSE': b'MIT\n'}
        self.refresh()

    def refresh(self):
        self.files[validator.MANIFEST] = json.dumps(validator.make_manifest(self.files)).encode()
        self.modes = {name: '100644' for name in self.files}

    def errors(self):
        return validator.validate(self.files, self.modes)

    def test_valid_distribution(self):
        self.assertEqual(self.errors(), [])

    def test_extra_file_is_rejected(self):
        self.files['extra.md'] = b'unreviewed'
        self.modes['extra.md'] = '100644'
        self.assertIn('manifest_does_not_match_exact_index', self.errors())

    def test_changed_content_is_rejected(self):
        self.files['LICENSE'] = b'changed'
        self.assertIn('manifest_does_not_match_exact_index', self.errors())

    def test_missing_manifest_is_rejected(self):
        del self.files[validator.MANIFEST]
        self.assertIn('invalid_manifest', self.errors())

    def test_duplicate_json_key_is_rejected(self):
        self.files[validator.MANIFEST] = b'{"schema_version":1,"schema_version":1,"files":[]}'
        self.assertIn('invalid_manifest', self.errors())

    def test_manifest_schema_requires_integer_not_boolean_or_float(self):
        for value in (True, 1.0):
            with self.subTest(value=value):
                manifest = validator.make_manifest(self.files)
                manifest['schema_version'] = value
                self.files[validator.MANIFEST] = json.dumps(manifest).encode()
                self.assertIn('invalid_manifest', self.errors())

    def test_symlink_and_gitlink_are_rejected(self):
        for mode in ('120000', '160000'):
            self.modes['LICENSE'] = mode
            self.assertIn('non_regular_git_mode:LICENSE', self.errors())

    def test_missing_local_dependency_is_rejected(self):
        self.files['README.md'] = b'[Missing](missing.md)'
        self.refresh()
        self.assertIn('unresolved_local_link:README.md', self.errors())

    def test_external_documentation_link_is_allowed(self):
        self.files['README.md'] = b'[Docs](https://docs.python.org/3/)'
        self.refresh()
        self.assertEqual(self.errors(), [])

    def test_personal_path_is_rejected_even_with_valid_manifest(self):
        self.files['README.md'] = ('C:' + '/' + 'Users' + '/' + 'sample-user' + '/private').encode()
        self.refresh()
        self.assertIn('personal_absolute_path:README.md', self.errors())

    def test_secret_is_rejected_even_with_valid_manifest(self):
        self.files['README.md'] = ('gh' + 'p_' + 'A' * 36).encode()
        self.refresh()
        self.assertIn('github_token:README.md', self.errors())

    def test_invalid_python_is_rejected(self):
        self.files['bad.py'] = b'def broken(:'
        self.refresh()
        self.assertIn('invalid_text_or_syntax:bad.py', self.errors())

    def test_binary_is_rejected(self):
        self.files['binary.md'] = bytes([255])
        self.refresh()
        self.assertTrue(any('binary.md' in error for error in self.errors()))

    def test_local_configuration_is_rejected(self):
        self.files['settings.local.json'] = b'{}'
        self.refresh()
        self.assertIn('credential_or_local_configuration_path:settings.local.json', self.errors())

    def test_skill_name_must_match_its_folder(self):
        self.files['skills/sample/SKILL.md'] = b'---\nname: different\ndescription: example\n---\n'
        self.refresh()
        self.assertIn('invalid_skill_frontmatter:skills/sample/SKILL.md', self.errors())

    def test_git_index_reader_uses_staged_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            for name, data in self.files.items():
                (root / name).write_bytes(data)
            subprocess.run(['git', '-C', str(root), '-c', 'core.autocrlf=false', 'add', '--', *self.files], check=True)
            (root / 'LICENSE').write_bytes(b'unstaged change')
            files, modes = validator.read_index(root)
            self.assertEqual(files['LICENSE'], b'MIT\n')
            self.assertEqual(validator.validate(files, modes), [])


if __name__ == '__main__':
    unittest.main()
