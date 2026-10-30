"""Check the immutable Git index, manifest closure and local document links."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import tomllib
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'PUBLICATION_MANIFEST.json'
spec = importlib.util.spec_from_file_location('distribution_guard', ROOT / 'skills/versionamento-projetos/scripts/guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def read_index(root):
    raw = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--stage', '-z'])
    files, modes = {}, {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        mode, oid, stage = metadata.decode('ascii').split()
        if stage != '0':
            raise ValueError('unmerged_index')
        path = name.decode('utf-8')
        modes[path] = mode
        files[path] = subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', oid])
    return files, modes


def make_manifest(files):
    return {'schema_version': 1, 'files': [
        {'path': path, 'sha256': hashlib.sha256(data).hexdigest()}
        for path, data in sorted(files.items()) if path != MANIFEST]}


def validate(files, modes):
    errors = []
    try:
        actual = json.loads(files[MANIFEST], object_pairs_hook=unique_object)
        if not isinstance(actual, dict) or type(actual.get('schema_version')) is not int or actual['schema_version'] != 1:
            raise ValueError('invalid_manifest_schema')
        if actual != make_manifest(files):
            errors.append('manifest_does_not_match_exact_index')
    except (KeyError, ValueError, UnicodeError):
        errors.append('invalid_manifest')
    for path, data in files.items():
        p = PurePosixPath(path)
        if p.is_absolute() or '..' in p.parts or '\\' in path:
            errors.append('invalid_path:' + path)
        if modes.get(path) not in {'100644', '100755'}:
            errors.append('non_regular_git_mode:' + path)
            continue
        errors.extend(label + ':' + path for label in guard.inspect_content(path, data))
        try:
            text = data.decode('utf-8')
            if re.search(r'(?i)\b[A-Z]:[\\/]+Users[\\/]+[^\\/\s]+|/(?:Users|home)/[^/\s]+', text):
                errors.append('personal_absolute_path:' + path)
            if p.suffix == '.json':
                json.loads(text, object_pairs_hook=unique_object)
            elif p.suffix == '.toml':
                tomllib.loads(text)
            elif p.suffix in {'.py', '.pyw'}:
                ast.parse(text)
            if p.name == 'SKILL.md':
                header = text.split('---', 2)
                if len(header) != 3 or not re.search(r'^name:\s*' + re.escape(p.parent.name) + r'\s*$', header[1], re.M) or not re.search(r'^description:\s*\S', header[1], re.M):
                    errors.append('invalid_skill_frontmatter:' + path)
            if p.suffix == '.md':
                for target in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', text):
                    parsed = urlsplit(target.strip('<>'))
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    resolved = posixpath.normpath(posixpath.join(str(p.parent), unquote(parsed.path)))
                    if resolved.startswith('../') or resolved.startswith('/') or resolved not in files:
                        errors.append('unresolved_local_link:' + path)
        except (ValueError, UnicodeError, SyntaxError):
            errors.append('invalid_text_or_syntax:' + path)
    return sorted(set(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-manifest', action='store_true')
    args = parser.parse_args()
    files, modes = read_index(ROOT)
    if args.write_manifest:
        (ROOT / MANIFEST).write_text(json.dumps(make_manifest(files), ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        print('Manifest written from staged Git objects; review and stage it before validation.')
        return 0
    errors = validate(files, modes)
    print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'tracked_files': len(files), 'errors': errors}))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
