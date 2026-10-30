from __future__ import annotations

from pathlib import Path, PurePosixPath
from datetime import date
import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit

DATA_SUFFIXES = {'.csv', '.tsv', '.parquet', '.xlsx', '.xls', '.pdf', '.docx',
                 '.mp3', '.mp4', '.wav', '.zip', '.db', '.sqlite', '.pkl', '.pickle'}
DENIED_PARTS = {'work', 'outputs', 'node_modules', '.venv', 'venv', '__pycache__',
                '.codex_tmp', 'transcricoes', 'transcripts', 'recordings', 'datasets'}
KEYS = [
    ('private_key', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    ('github_token', r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{35,})\b'),
    ('openai_key', r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b'),
    ('databricks_token', r'\bdapi[a-fA-F0-9]{32}\b'),
    ('aws_access_key', r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
]
REVIEW_LIMIT = 2_000_000
BATCH_BYTES = 16_000_000
SHA = re.compile(r'^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$')
REGISTRY = Path(__file__).resolve().parents[1] / 'references/ambiente-repos.local.json'
GH = Path(os.environ.get('GH_CLI', 'gh'))


class PublicationPolicyError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def publication_policy(registry: dict) -> dict:
    """No implicit publication permission, including in a portable checkout."""
    if not isinstance(registry, dict) or not isinstance(registry.get('projects'), list):
        raise PublicationPolicyError('PUBLICATION_REGISTRY_INVALID')
    policy = registry.get('publication_policy')
    if policy is None:
        raise PublicationPolicyError('PUBLICATION_POLICY_MISSING')
    if (not isinstance(policy, dict) or policy.get('mode') not in {'LOCAL_ONLY', 'PRIVATE_REMOTE_ALLOWED', 'PRIVATE_SELECTED'}
            or policy.get('source') != 'DIRECT_USER_DECISION'
            or not isinstance(policy.get('as_of'), str)
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', policy['as_of'])
            or type(policy.get('create_remote')) is not bool or type(policy.get('push')) is not bool
            or (policy['mode'] in {'LOCAL_ONLY', 'PRIVATE_SELECTED'} and (policy['create_remote'] or policy['push']))):
        raise PublicationPolicyError('PUBLICATION_POLICY_INVALID')
    try:
        date.fromisoformat(policy['as_of'])
    except ValueError:
        raise PublicationPolicyError('PUBLICATION_POLICY_INVALID') from None
    exceptions = policy.get('public_exceptions', [])
    if not isinstance(exceptions, list) or len(exceptions) > 1:
        raise PublicationPolicyError('PUBLICATION_PUBLIC_EXCEPTION_INVALID')
    for exception in exceptions:
        if (not isinstance(exception, dict)
                or set(exception) != {'project_id', 'repository', 'source', 'scope',
                                      'audited_tree', 'manifest_sha256'}
                or policy['mode'] != 'PRIVATE_SELECTED'
                or not isinstance(exception.get('project_id'), str) or not exception['project_id']
                or exception.get('source') != 'DIRECT_USER_DECISION'
                or exception.get('scope') != 'AUDITED_GENERIC_SKILLS_AGENTS'
                or not isinstance(exception.get('repository'), str)
                or repository_identity('https://github.com/' + exception['repository']) != exception['repository'].casefold()
                or exception['repository'].split('/')[0].casefold() != str(registry.get('github_owner', '')).casefold()
                or not isinstance(exception.get('audited_tree'), str)
                or not SHA.fullmatch(exception['audited_tree'])
                or set(exception['audited_tree']) == {'0'}
                or not isinstance(exception.get('manifest_sha256'), str)
                or not re.fullmatch(r'[0-9a-fA-F]{64}', exception['manifest_sha256'])):
            raise PublicationPolicyError('PUBLICATION_PUBLIC_EXCEPTION_INVALID')
    if policy['mode'] == 'PRIVATE_SELECTED':
        selections = policy.get('selections')
        if not isinstance(selections, list):
            raise PublicationPolicyError('PUBLICATION_SELECTION_INVALID')
        ids, projects = set(), set()
        for selection in selections:
            if not isinstance(selection, dict):
                raise PublicationPolicyError('PUBLICATION_SELECTION_INVALID')
            update = selection.get('update')
            repository = selection.get('repository')
            owner = registry.get('github_owner')
            if (not isinstance(selection.get('id'), str) or not selection['id']
                    or not isinstance(selection.get('project_id'), str) or not selection['project_id']
                    or selection['id'] in ids or selection['project_id'] in projects
                    or not isinstance(repository, str) or not isinstance(owner, str) or not owner
                    or repository_identity('https://github.com/' + repository) != repository.casefold()
                    or repository.split('/')[0].casefold() != owner.casefold()
                    or selection.get('visibility') not in {'private', 'public'}
                    or type(selection.get('create_remote')) is not bool or not isinstance(update, dict)
                    or not isinstance(update.get('local_sha'), str) or not SHA.fullmatch(update['local_sha'])
                    or set(update['local_sha']) == {'0'}
                    or not isinstance(update.get('expected_remote_sha'), str)
                    or not SHA.fullmatch(update['expected_remote_sha'])
                    or len(update['local_sha']) != len(update['expected_remote_sha'])
                    or not valid_branch_ref(update.get('remote_ref'))):
                raise PublicationPolicyError('PUBLICATION_SELECTION_INVALID')
            if selection['visibility'] == 'public':
                public_exception(registry, selection, validated_policy=policy)
            ids.add(selection['id'])
            projects.add(selection['project_id'])
    elif policy.get('selections'):
        raise PublicationPolicyError('PUBLICATION_SELECTION_INVALID')
    return policy


def public_exception(registry, selection, validated_policy=None):
    """Resolve the single public distribution exception without broadening defaults."""
    policy = validated_policy if validated_policy is not None else publication_policy(registry)
    matches = [item for item in policy.get('public_exceptions', [])
               if item['project_id'] == selection['project_id']
               and item['repository'].casefold() == selection['repository'].casefold()]
    projects = [item for item in registry['projects']
                if isinstance(item, dict) and item.get('id') == selection['project_id']]
    if (len(matches) != 1 or len(projects) != 1
            or projects[0].get('classification') != 'public_generic_distribution'
            or str(projects[0].get('github_repo', '')).casefold() != selection['repository'].casefold()):
        raise PublicationPolicyError('PUBLICATION_PUBLIC_EXCEPTION_REQUIRED')
    return matches[0]


def valid_branch_ref(value):
    return (isinstance(value, str) and value.startswith('refs/heads/')
            and bool(re.fullmatch(r'refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]*', value))
            and not any(x in value for x in ('..', '//', '@{'))
            and all(part and not part.startswith('.') and not part.endswith(('.', '.lock'))
                    for part in value.split('/')))


def repository_identity(url):
    """Credential-free github.com URL identity; no implicit host or URL rewriting."""
    if not isinstance(url, str):
        return None
    if url.startswith('git@github.com:'):
        path = url[len('git@github.com:'):]
    else:
        try:
            parsed = urlsplit(url)
            if parsed.hostname != 'github.com' or parsed.query or parsed.fragment:
                return None
            if parsed.scheme == 'https':
                if parsed.username or parsed.password or parsed.port not in {None, 443}:
                    return None
            elif parsed.scheme == 'ssh':
                if parsed.username != 'git' or parsed.password or parsed.port not in {None, 22}:
                    return None
            else:
                return None
            path = parsed.path.lstrip('/')
        except ValueError:
            return None
    path = path.rstrip('/').removesuffix('.git')
    return path.casefold() if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+', path) else None


def publication_selection(registry, project):
    """Resolve a fresh, unique grant against the registered project identity."""
    policy = publication_policy(registry)
    if policy['mode'] != 'PRIVATE_SELECTED':
        return None
    matches = [p for p in registry['projects'] if isinstance(p, dict) and p.get('id') == project.get('id')]
    grants = [s for s in policy['selections'] if s['project_id'] == project.get('id')]
    if len(matches) != 1 or len(grants) != 1:
        raise PublicationPolicyError('PUBLICATION_NOT_SELECTED')
    current, selection = matches[0], grants[0]
    for item in (current, project):
        if (not isinstance(item.get('repo_root'), str) or not Path(item['repo_root']).is_absolute()
                or normalized_root(item['repo_root']) != normalized_root(current['repo_root'])
                or not isinstance(item.get('github_repo'), str)
                or item['github_repo'].casefold() != selection['repository'].casefold()):
            raise PublicationPolicyError('PUBLICATION_SELECTION_IDENTITY_MISMATCH')
        if selection['visibility'] == 'public' and item.get('classification') != 'public_generic_distribution':
            raise PublicationPolicyError('PUBLICATION_PUBLIC_EXCEPTION_REQUIRED')
    return selection


def private_destination_denial(repository):
    return destination_denial(repository, 'private')


def destination_denial(repository, visibility):
    """Fresh authenticated checks on github.com; never report raw command output."""
    try:
        payloads = []
        for endpoint in ('user', 'repos/' + repository):
            response = subprocess.run([str(GH), 'api', endpoint, '--hostname', 'github.com'],
                                      capture_output=True, text=True, encoding='utf-8', timeout=30)
            if response.returncode:
                return 'PUBLICATION_DESTINATION_UNVERIFIABLE'
            payload = json.loads(response.stdout)
            if not isinstance(payload, dict):
                return 'PUBLICATION_DESTINATION_UNVERIFIABLE'
            payloads.append(payload)
        user, repo = payloads
        if str(user.get('login', '')).casefold() != repository.split('/')[0].casefold():
            return 'AUTHENTICATED_OWNER_MISMATCH'
        if repo.get('private') is not (visibility == 'private'):
            return 'REPOSITORY_NOT_PRIVATE' if visibility == 'private' else 'REPOSITORY_NOT_PUBLIC'
        if (str(repo.get('full_name', '')).casefold() != repository.casefold()
                or repository_identity(repo.get('html_url')) != repository.casefold()):
            return 'REPOSITORY_IDENTITY_MISMATCH'
    except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError):
        return 'PUBLICATION_DESTINATION_UNVERIFIABLE'
    return None


def selected_destination_denial(repository, visibility):
    # Keep the private verification entrypoint for existing consumers and tests.
    return (private_destination_denial(repository) if visibility == 'private'
            else destination_denial(repository, 'public'))


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def verify_public_content(root, selection, exception):
    """Verify immutable selected bytes against the explicitly audited Git tree.

    The public manifest describes every regular blob except itself. Neither a
    clean worktree nor a file-name regex is an audit authorization.
    """
    sha = selection['update']['local_sha']
    try:
        if git(root, 'cat-file', '-t', sha).strip() != b'commit':
            raise PublicationPolicyError('PUBLICATION_COMMIT_REQUIRED')
        tree = git(root, 'rev-parse', sha + '^{tree}').decode('ascii').strip()
        if tree.casefold() != exception['audited_tree'].casefold():
            raise PublicationPolicyError('PUBLICATION_AUDITED_TREE_MISMATCH')
        entries = {}
        for entry in filter(None, git(root, 'ls-tree', '-r', '-z', '--full-tree', sha).split(b'\0')):
            metadata, name_bytes = entry.split(b'\t', 1)
            mode, kind, oid = metadata.decode('ascii').split()
            name = name_bytes.decode('utf-8')
            if mode not in {'100644', '100755'} or kind != 'blob':
                raise PublicationPolicyError('PUBLICATION_PUBLIC_TREE_MODE_INVALID')
            entries[name] = oid
        manifest_name = 'PUBLICATION_MANIFEST.json'
        if manifest_name not in entries:
            raise PublicationPolicyError('PUBLICATION_MANIFEST_INVALID')
        oid = entries.pop(manifest_name)
        size = int(git(root, 'cat-file', '-s', oid))
        if size > REVIEW_LIMIT:
            raise PublicationPolicyError('PUBLICATION_MANIFEST_INVALID')
        raw = git(root, 'cat-file', 'blob', oid)
        if hashlib.sha256(raw).hexdigest() != exception['manifest_sha256'].casefold():
            raise PublicationPolicyError('PUBLICATION_MANIFEST_HASH_MISMATCH')
        manifest = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_json_object)
        if (not isinstance(manifest, dict) or set(manifest) != {'schema_version', 'files'}
                or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
                or not isinstance(manifest.get('files'), list)):
            raise PublicationPolicyError('PUBLICATION_MANIFEST_INVALID')
        expected = {}
        for item in manifest['files']:
            if (not isinstance(item, dict) or set(item) != {'path', 'sha256'}
                    or not isinstance(item.get('path'), str)
                    or not item['path'] or '\\' in item['path'] or '\0' in item['path']
                    or item['path'].startswith('/') or PurePosixPath(item['path']).as_posix() != item['path']
                    or any(part in {'.', '..', '.git'} for part in PurePosixPath(item['path']).parts)
                    or item['path'] == manifest_name or item['path'] in expected
                    or not isinstance(item.get('sha256'), str)
                    or not re.fullmatch(r'[0-9a-fA-F]{64}', item['sha256'])):
                raise PublicationPolicyError('PUBLICATION_MANIFEST_INVALID')
            expected[item['path']] = item['sha256'].casefold()
        if set(entries) != set(expected):
            raise PublicationPolicyError('PUBLICATION_MANIFEST_TREE_MISMATCH')
        # Reuse the bounded blob reader used by staged/history review. Hashing
        # each file via separate Git processes would scale poorly for a catalog.
        findings = inspect_entries(root, [(name, '100644', oid) for name, oid in entries.items()],
                                   expected_digests=expected)
        labels = {label for issues in findings for label in issues}
        if 'public_manifest_content_mismatch' in labels:
            raise PublicationPolicyError('PUBLICATION_MANIFEST_CONTENT_MISMATCH')
        if 'file_exceeds_2MB_review_limit' in labels:
            raise PublicationPolicyError('PUBLICATION_PUBLIC_BLOB_TOO_LARGE')
        if labels:
            raise PublicationPolicyError('PUBLICATION_PUBLIC_CONTENT_REQUIRES_REVIEW')
    except PublicationPolicyError:
        raise
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError, UnicodeError, TypeError):
        raise PublicationPolicyError('PUBLICATION_PUBLIC_CONTENT_UNVERIFIABLE') from None


def normalized_root(value: str | Path) -> str:
    return os.path.normcase(str(Path(value).resolve()))


def push_policy_denial(root: Path, updates='', remote_url=None, verify_destination=True) -> dict | None:
    """Exact registered roots only; missing/invalid portable maps deny push.

    This is enforcement by this pre-push hook, not a network access control.
    Other tools can ignore hooks, so it is not a universal publication barrier.
    """
    scope = 'Pre-push hook for exact registered repository roots; not network access control'
    try:
        registry = json.loads(REGISTRY.read_text(encoding='utf-8-sig'))
        policy = publication_policy(registry)
        roots = []
        for project in registry['projects']:
            if (not isinstance(project, dict) or not isinstance(project.get('repo_root'), str)
                    or not project['repo_root'] or not Path(project['repo_root']).is_absolute()):
                raise PublicationPolicyError('PUBLICATION_REGISTRY_INVALID')
            roots.append(normalized_root(project['repo_root']))
        if len(set(roots)) != len(roots):
            raise PublicationPolicyError('PUBLICATION_REGISTRY_INVALID')
        if policy['mode'] == 'PRIVATE_SELECTED':
            matches = [p for p in registry['projects'] if normalized_root(p['repo_root']) == normalized_root(root)]
            if len(matches) != 1:
                raise PublicationPolicyError('PUBLICATION_NOT_SELECTED')
            selection = publication_selection(registry, matches[0])
            rows = [line.split() for line in updates.splitlines()]
            update = selection['update']
            if (len(rows) != 1 or len(rows[0]) != 4
                    or rows[0][1].casefold() != update['local_sha'].casefold()
                    or rows[0][2] != update['remote_ref']
                    or rows[0][3].casefold() != update['expected_remote_sha'].casefold()
                    or repository_identity(remote_url) != selection['repository'].casefold()):
                raise PublicationPolicyError('PUBLICATION_UPDATE_NOT_SELECTED')
            if git(root, 'cat-file', '-t', rows[0][1]).strip() != b'commit':
                raise PublicationPolicyError('PUBLICATION_COMMIT_REQUIRED')
            if set(rows[0][3]) != {'0'}:
                ancestor = subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor',
                                           rows[0][3], rows[0][1]], capture_output=True, timeout=30)
                if ancestor.returncode:
                    raise PublicationPolicyError('PUBLICATION_NON_FAST_FORWARD')
            if selection['visibility'] == 'public':
                verify_public_content(root, selection, public_exception(registry, selection))
            if verify_destination:
                code = selected_destination_denial(selection['repository'], selection['visibility'])
                if code:
                    raise PublicationPolicyError(code)
            return None
    except (OSError, ValueError) as error:
        return {'code': getattr(error, 'code', 'PUBLICATION_REGISTRY_UNAVAILABLE_OR_INVALID'),
                'scope': scope, 'action': 'push', 'policy_state': 'UNVERIFIABLE'}
    if normalized_root(root) not in roots:
        return None
    if not policy['push']:
        return {'code': 'PUBLICATION_LOCAL_ONLY' if policy['mode'] == 'LOCAL_ONLY' else 'PUSH_DISABLED_BY_POLICY',
                'scope': scope, 'action': 'push', 'policy_state': policy['mode']}
    return None


def secret_issues(text: str) -> list[str]:
    return [label for label, pattern in KEYS if re.search(pattern, text)]


def inspect_content(name: str, data: bytes) -> list[str]:
    # Git paths always use '/', including when the guard runs on Windows.
    p = PurePosixPath(name)
    issues = []
    if p.suffix.lower() in DATA_SUFFIXES:
        issues.append('data_or_document_requires_separate_policy')
    if {part.lower() for part in p.parts} & DENIED_PARTS:
        issues.append('generated_or_private_directory')
    if ((p.name.lower().startswith('.env') and p.name.lower() != '.env.example')
            or p.suffix.lower() in {'.pem', '.key', '.pfx', '.p12'}
            or p.name.lower() in {'credentials', 'hosts.yml'} or '.local.' in p.name.lower()):
        issues.append('credential_or_local_configuration_path')
    if len(data) > REVIEW_LIMIT:
        issues.append('file_exceeds_2MB_review_limit')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return sorted(set(issues + ['binary_or_non_utf8_requires_review']))
    issues.extend(secret_issues(text))
    if p.suffix.lower() == '.ipynb':
        try:
            obj = json.loads(text)
            if not isinstance(obj, dict) or not isinstance(obj.get('cells'), list):
                issues.append('invalid_notebook_json')
            elif any(not isinstance(c, dict) for c in obj['cells']):
                issues.append('invalid_notebook_json')
            elif any(c.get('outputs') or c.get('execution_count') is not None for c in obj['cells']):
                issues.append('notebook_contains_outputs_or_execution_state')
        except (ValueError, TypeError):
            issues.append('invalid_notebook_json')
    return sorted(set(issues))


def git(root, *args, input=None):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                          input=input, check=True, timeout=60).stdout


def inspect_blob(root: Path, name: str, mode: str, oid: str) -> list[str]:
    return inspect_entries(root, [(name, mode, oid)])[0]


def inspect_entries(root: Path, entries: list[tuple[str, str, str]],
                    expected_digests: dict[str, str] | None = None) -> list[list[str]]:
    """Inspect immutable Git modes/OIDs using bounded batches, never worktree files.

    Check every unique regular blob once for size/type, then read eligible blobs
    in batches capped by their aggregate size. Policy remains path dependent:
    identical content under safe.py and outputs/safe.py is checked for both paths.
    """
    results = [[] for _ in entries]
    regular = {}
    for index, (name, mode, oid) in enumerate(entries):
        if mode == '120000':
            results[index] = ['symlink_requires_review']
        elif mode == '160000':
            results[index] = ['gitlink_requires_separate_review']
        elif mode not in {'100644', '100755'}:
            results[index] = ['unsupported_git_mode']
        else:
            if not SHA.fullmatch(oid):
                raise ValueError('invalid Git object id')
            regular.setdefault(oid, []).append((index, name))
    if not regular:
        return results
    oids = list(regular)
    request = ''.join(oid + '\n' for oid in oids).encode('ascii')
    lines = git(root, 'cat-file', '--batch-check', input=request).splitlines()
    if len(lines) != len(oids):
        raise ValueError('incomplete Git batch metadata')
    eligible = []
    for oid, line in zip(oids, lines):
        fields = line.split()
        if len(fields) != 3 or fields[0].decode('ascii') != oid or fields[1] != b'blob':
            raise ValueError('invalid Git blob metadata')
        size = int(fields[2])
        if size < 0:
            raise ValueError('invalid Git blob size')
        if size > REVIEW_LIMIT:
            for index, name in regular[oid]:
                results[index] = ['file_exceeds_2MB_review_limit']
        else:
            eligible.append((oid, size))
    batch = []
    batch_size = 0
    for item in eligible + [(None, 0)]:
        oid, size = item
        if batch and (oid is None or batch_size + size + 128 > BATCH_BYTES):
            raw = git(root, 'cat-file', '--batch',
                      input=''.join(key + '\n' for key, _ in batch).encode('ascii'))
            offset = 0
            for key, expected_size in batch:
                end = raw.find(b'\n', offset)
                fields = raw[offset:end].split() if end >= 0 else []
                if (len(fields) != 3 or fields[0].decode('ascii') != key
                        or fields[1] != b'blob' or int(fields[2]) != expected_size):
                    raise ValueError('invalid Git batch content header')
                offset = end + 1
                data = raw[offset:offset + expected_size]
                offset += expected_size
                if len(data) != expected_size or raw[offset:offset + 1] != b'\n':
                    raise ValueError('incomplete Git batch content')
                offset += 1
                for index, name in regular[key]:
                    results[index] = inspect_content(name, data)
                    if expected_digests is not None and hashlib.sha256(data).hexdigest() != expected_digests.get(name):
                        results[index].append('public_manifest_content_mismatch')
            if offset != len(raw):
                raise ValueError('unexpected Git batch content')
            batch = []
            batch_size = 0
        if oid is not None:
            batch.append(item)
            batch_size += size + 128
    return results


def inspect_index(root: Path):
    changed = set(filter(None, git(root, 'diff', '--cached', '--name-only',
                                  '--diff-filter=ACMRTU', '-z').decode('utf-8').split('\0')))
    findings = []
    entries = []
    for entry in filter(None, git(root, 'ls-files', '--stage', '-z').split(b'\0')):
        metadata, name_bytes = entry.split(b'\t', 1)
        mode, oid, stage = metadata.decode('ascii').split()
        name = name_bytes.decode('utf-8')
        if name not in changed:
            continue
        if stage != '0':
            findings.append({'path': name, 'issues': ['unmerged_index_entry']})
        else:
            entries.append((name, mode, oid))
    for (name, mode, oid), issues in zip(entries, inspect_entries(root, entries)):
        if issues:
            findings.append({'path': name, 'issues': issues})
    return findings


def inspect_push(root: Path, updates: str):
    """Read native pre-push stdin and inspect every outgoing commit tree.

    For a new remote ref, review all reachable history conservatively: stdin
    cannot establish which objects exist under other remote refs.
    Existing refs review commits reachable from local SHA but not old SHA.
    Include intermediate commits even when HEAD later removes a secret.
    """
    findings = []
    commits = set()
    seen_blobs = set()
    entries = []
    entry_commits = []
    for line in updates.splitlines():
        fields = line.split()
        if len(fields) != 4 or not SHA.fullmatch(fields[1]) or not SHA.fullmatch(fields[3]):
            raise ValueError('invalid pre-push input')
        local_ref, local_sha, remote_ref, remote_sha = fields
        if set(local_sha) == {'0'}:  # A deletion sends no new file content.
            continue
        obj = local_sha
        while git(root, 'cat-file', '-t', obj).strip() == b'tag':
            tag = git(root, 'cat-file', 'tag', obj).decode('utf-8')
            issues = secret_issues(tag)
            if issues:
                findings.append({'ref': local_ref, 'path': '(tag metadata)', 'issues': issues})
            obj = tag.splitlines()[0].removeprefix('object ')
        if git(root, 'cat-file', '-t', obj).strip() != b'commit':
            findings.append({'ref': local_ref, 'path': '(ref target)',
                             'issues': ['non_commit_ref_requires_review']})
            continue
        args = ['rev-list', local_sha]
        if set(remote_sha) != {'0'}:
            args.extend(['--not', remote_sha])
        commits.update(git(root, *args).decode('ascii').splitlines())
    for commit in sorted(commits):
        metadata = git(root, 'cat-file', 'commit', commit).decode('utf-8')
        issues = secret_issues(metadata)
        if issues:
            findings.append({'commit': commit, 'path': '(commit metadata)', 'issues': issues})
        for entry in filter(None, git(root, 'ls-tree', '-r', '-z', '--full-tree', commit).split(b'\0')):
            metadata_bytes, name_bytes = entry.split(b'\t', 1)
            mode, kind, oid = metadata_bytes.decode('ascii').split()
            name = name_bytes.decode('utf-8')
            key = (name, mode, oid)
            if key in seen_blobs:
                continue
            seen_blobs.add(key)
            entries.append((name, mode, oid))
            entry_commits.append(commit)
    for commit, (name, mode, oid), issues in zip(entry_commits, entries, inspect_entries(root, entries)):
        if issues:
            findings.append({'commit': commit, 'path': name, 'issues': issues})
    return findings


def check_sources(root: Path, paths: list[str]):
    result = []
    for name in paths:
        p = (root / name).resolve()
        if not p.is_relative_to(root.resolve()):
            raise ValueError('path outside project')
        if not p.is_file():
            continue
        issues = inspect_content(name, p.read_bytes())
        if p.suffix.lower() in {'.py', '.pyw'}:
            try:
                ast.parse(p.read_text(encoding='utf-8-sig'), filename=name)
            except (SyntaxError, UnicodeError):
                issues.append('python_parse_failed')
        result.append({'path': name, 'issues': issues})
    return result


def main():
    parser = argparse.ArgumentParser(description='Review Git objects; never adds, commits or pushes')
    parser.add_argument('--root', default='.')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--pre-push', action='store_true', help='Read native pre-push ref updates from stdin')
    parser.add_argument('--remote-name')
    parser.add_argument('--remote-url')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    scope = ('Outgoing commit trees and commit/tag metadata; new refs include all reachable history'
             if args.pre_push else 'Changed staged Git objects and modes')
    try:
        if args.pre_push:
            # Native hooks run at the repo root; resolving also prevents --root
            # pointing to a subdirectory from evading exact-root matching.
            root = Path(git(root, 'rev-parse', '--show-toplevel').decode('utf-8').strip()).resolve()
            updates = sys.stdin.read()
            denial = push_policy_denial(root, updates, args.remote_url)
            if denial:
                report = {'status': 'BLOCKED', 'findings': [{'path': '(publication policy)', 'issues': [denial['code']]}],
                          'scope': denial['scope'], 'publication_policy': denial,
                          'limitation': 'Other tools may ignore hooks; this does not replace network controls'}
                print(json.dumps(report, ensure_ascii=True, indent=2) if args.json
                      else 'BLOCKED ' + denial['code'])
                return 1 if denial['policy_state'] != 'UNVERIFIABLE' else 2
        issues = inspect_push(root, updates) if args.pre_push else inspect_index(root)
        if args.pre_push and not issues:
            # A revocation during content review must still stop the update.
            denial = push_policy_denial(root, updates, args.remote_url, verify_destination=False)
            if denial:
                issues.append({'path': '(publication policy)', 'issues': [denial['code']]})
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, UnicodeError):
        # Never echo Git output, excerpts, URLs or secret values.
        print('Git guard could not complete verification; operation blocked', file=sys.stderr)
        return 2
    report = {'status': 'BLOCKED' if issues else 'PASS', 'findings': issues,
              'scope': scope, 'limitation': 'Heuristic checks do not prove absence of sensitive data'}
    print(json.dumps(report, ensure_ascii=True, indent=2) if args.json
          else report['status'] + (' ' + json.dumps(issues, ensure_ascii=True) if issues else ' Git objects checked'))
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())

