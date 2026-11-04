"""Inspect downloaded archives without extracting large or untrusted paths."""

import json
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def safe_name(name):
    normalized = name.replace('\\', '/')
    path = PurePosixPath(normalized)
    return not path.is_absolute() and '..' not in path.parts and ':' not in normalized


def read_sample(stream):
    # Limit bytes rather than trusting newlines in an arbitrary archive member.
    return stream.read(2048).decode('utf-8', errors='replace').splitlines()[:2]


def inspect(item):
    path = ROOT / item['local_path']
    entries, samples, log_bytes = [], {}, 0
    complete = item['name'] != 'Thunderbird'
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                entries.append(dict(name=member.filename, bytes=member.file_size,
                                    safe_relative_path=safe_name(member.filename)))
                if member.filename.endswith('.log'):
                    log_bytes += member.file_size
                if len(samples) < 2 and not member.is_dir() and member.filename.endswith(('.log', '.csv', '.txt')):
                    with archive.open(member) as stream:
                        samples[member.filename] = read_sample(stream)
    else:
        with tarfile.open(path, mode='r|gz') as archive:
            for member in archive:
                entries.append(dict(name=member.name, bytes=member.size,
                                    safe_relative_path=safe_name(member.name),
                                    regular_file=member.isfile()))
                if member.name.endswith('.log') and member.isfile():
                    log_bytes += member.size
                if len(samples) < 2 and member.isfile():
                    with archive.extractfile(member) as stream:
                        samples[member.name] = read_sample(stream)
                if not complete:
                    break  # Read the large log header/sample without decompressing 30 GiB.
    return dict(id=item['id'], name=item['name'], archive_bytes=path.stat().st_size,
                listing_complete=complete, listed_member_count=len(entries),
                listed_content_bytes=sum(e['bytes'] for e in entries),
                listed_log_bytes=log_bytes, entries=entries, samples=samples)


def main():
    manifest = json.loads((ROOT/'docs/research/datasets.json').read_text(encoding='utf-8'))
    result = [inspect(item) for item in manifest['datasets'] if item['artifact_downloaded']]
    (ROOT/'docs/research/archive_inventory.json').write_text(
        json.dumps(result, indent=2, ensure_ascii=False)+'\n',encoding='utf-8')
    for item in result:
        print(item['name'], item['archive_bytes'], item['listed_log_bytes'],
              'full listing' if item['listing_complete'] else 'first member only')


if __name__ == '__main__':
    main()
