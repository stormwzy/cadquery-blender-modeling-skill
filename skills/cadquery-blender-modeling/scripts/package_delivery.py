"""Package explicit delivery files, SHA-256 manifest, and verify the ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def package(manifest_path, output):
    root = manifest_path.resolve().parent
    data = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    selected = data.get('delivery_files', [])
    if not selected or len(selected) != len(set(selected)):
        raise ValueError('Delivery list must be nonempty and contain unique files')
    contents = {}
    for relative in selected:
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Missing or out-of-directory delivery file: {relative}')
        if path == output.resolve():
            raise ValueError('ZIP cannot contain itself')
        name = path.relative_to(root).as_posix()
        if name == 'SHA256SUMS.json' or name in contents:
            raise ValueError('Duplicate or reserved archive name')
        contents[name] = path.read_bytes()
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}
    hash_content = json.dumps({'algorithm': 'SHA-256', 'files': hashes}, indent=2).encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
        archive.writestr('SHA256SUMS.json', hash_content)
    with zipfile.ZipFile(output) as archive:
        if len(archive.namelist()) != len(contents) + 1 or set(archive.namelist()) != set(contents) | {'SHA256SUMS.json'}:
            raise ValueError('Archive file list mismatch')
        if archive.read('SHA256SUMS.json') != hash_content or archive.testzip() is not None:
            raise ValueError('Archive checksum manifest or CRC mismatch')
        for name, digest in hashes.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f'Archive content mismatch: {name}')
    print(json.dumps({'archive': str(output), 'files': len(contents),
                      'sha256_verified': True}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package(args.manifest, args.output)


if __name__ == '__main__':
    main()
