"""Audit and build a credential-free Windows runtime and source release."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

SKIP_DIRS = {'.git', '__pycache__', '.test-temp', '.pytest_cache', '.venv', 'outputs', 'media', 'cache'}
DATA_COOKIE = re.compile(r'(?i)(?:^|[-_.])cookies?(?:[-_.].*)?\.(?:txt|json|db|sqlite|sqlite3)$')
EXACT_PRIVATE = {'Cookies', 'Cookies-journal', 'Local State', 'Login Data', 'Web Data', 'History', 'token', 'credentials.json', 'auth.json'}
SECRET = re.compile(r'(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{35,}|sk-(?:proj-)?[A-Za-z0-9_-]{35,}|hf_[A-Za-z0-9]{30,})')
TEXT_EXT = {'.py', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.cmd', '.sh'}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def select(root, source=False):
    chosen = []
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if source and 'runtime' in rel.parts:
            continue
        if path.is_symlink():
            raise ValueError('Symlink refused: ' + str(rel))
        if not path.is_file():
            continue
        if path.name in EXACT_PRIVATE or DATA_COOKIE.search(path.name) or path.name.startswith('.env'):
            raise ValueError('Credential/browser-data filename refused: ' + str(rel))
        if path.suffix in {'.pyc', '.pyo'} or path.name in {'direct_url.json', 'runtime-manifest.json'}:
            continue
        if path.suffix.lower() in TEXT_EXT and path.stat().st_size <= 8 * 1024 * 1024:
            text = path.read_text(encoding='utf-8', errors='replace')
            if SECRET.search(text):
                raise ValueError('Token-shaped content refused: ' + str(rel))
        chosen.append(path)
    return chosen


def archive(root, files, target, prefix):
    temporary = target.with_suffix('.partial.zip')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for path in files:
            z.write(path, str(Path(prefix) / path.relative_to(root)))
    with zipfile.ZipFile(temporary) as z:
        bad = z.testzip()
        if bad:
            raise ValueError('Archive CRC check failed: ' + bad)
    temporary.replace(target)
    return {'path': target.name, 'size': target.stat().st_size, 'sha256': sha(target)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', required=True)
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args()
    release = Path(args.release).absolute()
    runtime = release / 'douyin-media-win64-full'
    source = release / 'source'
    runtime_files = select(runtime)
    source_files = select(source, source=True)
    report = {'privacy_audit_passed': True, 'runtime_files': len(runtime_files),
              'runtime_bytes': sum(p.stat().st_size for p in runtime_files),
              'source_files': len(source_files), 'cookies_or_credentials_included': False,
              'excluded_categories': sorted(SKIP_DIRS), 'assets': []}
    (release / 'package-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.audit_only:
        print(json.dumps(report, indent=2))
        return
    manifest = {'schema_version': 1, 'files': [{'path': str(p.relative_to(runtime)).replace('\\', '/'),
                 'size': p.stat().st_size, 'sha256': sha(p)} for p in runtime_files]}
    manifest_path = runtime / 'runtime-manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    runtime_files.append(manifest_path)
    report['assets'].append(archive(runtime, runtime_files, release / 'douyin-media-win64-full.zip', runtime.name))
    report['assets'].append(archive(source, source_files, release / 'douyin-media-source.zip', 'douyin-media-source'))
    (release / 'SHA256SUMS.txt').write_text(''.join(a['sha256'] + '  ' + a['path'] + '\n' for a in report['assets']), encoding='ascii')
    report['assets'].append({'path': 'SHA256SUMS.txt', 'size': (release / 'SHA256SUMS.txt').stat().st_size,
                              'sha256': sha(release / 'SHA256SUMS.txt')})
    (release / 'package-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
