"""Download cataloged public artifacts and verify provider dataset checksums."""

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'docs/research/datasets.json'
PAPERS = [
    ('P01', 'loghub', 'https://arxiv.org/pdf/2008.06448v3'),
    ('P02', 'hdfs_origin', 'https://people.eecs.berkeley.edu/~jordan/papers/xu-etal-sosp09.pdf'),
    ('P03', 'supercomputers', 'https://citeseerx.ist.psu.edu/document?doi=01b5c01835a57f63c250b4eed923b7f736707624&repid=rep1&type=pdf'),
    ('P04', 'deeplog', 'https://acmccs.github.io/papers/p1285-duA.pdf'),
    ('P05', 'drain', 'https://pinjiahe.github.io/files/pdf/research/ICWS17.pdf'),
    ('P06', 'neurallog', 'https://arxiv.org/pdf/2108.01955v3'),
    ('P07', 'lightad', 'https://boxiyu.github.io/assets/pdf/LightAD.pdf'),
    ('P08', 'critical_review', 'https://www.skopik.at/ait/2024_fse.pdf'),
    ('P09', 'loghub2', 'https://arxiv.org/pdf/2308.10828v2'),
]


def hashes(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            md5.update(chunk)
            sha.update(chunk)
    return md5.hexdigest(), sha.hexdigest()


def fetch(item):
    key, url, destination, expected = item
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + '.part')
    try:
        if not destination.exists():
            result = subprocess.run([
                'curl.exe', '--fail', '--location', '--retry', '3',
                '--retry-delay', '3', '--connect-timeout', '30',
                '--max-time', '3600', '--silent', '--show-error',
                '--output', str(partial), url,
            ], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr.strip()[-500:])
            if destination.suffix == '.pdf':
                with partial.open('rb') as stream:
                    if not stream.read(5).startswith(b'%PDF-'):
                        raise ValueError('Response is not a PDF')
            md5, sha = hashes(partial)
            if expected and md5 != expected:
                raise ValueError(f'MD5 mismatch: {md5}')
            partial.replace(destination)
        else:
            md5, sha = hashes(destination)
            if expected and md5 != expected:
                raise ValueError(f'MD5 mismatch: {md5}')
        return dict(id=key, status='verified', path=str(destination.relative_to(ROOT)),
                    bytes=destination.stat().st_size, md5=md5, sha256=sha, url=url)
    except Exception as exc:
        return dict(id=key, status='failed', error=str(exc), url=url)


def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    work = [(d['id'], d['download_url'], ROOT/'data/raw'/d['archive_name'],
             d['provider_md5']) for d in manifest['datasets']]
    work += [(key, url, ROOT/'research/papers'/f'{key}_{name}.pdf', None)
             for key, name, url in PAPERS]
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(fetch, item) for item in work]):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
            (ROOT/'docs/research/download_status.json').write_text(
                json.dumps(results, indent=2) + '\n', encoding='utf-8')
            for dataset in manifest['datasets']:
                if dataset['id'] == result['id']:
                    dataset['artifact_downloaded'] = result['status'] == 'verified'
                    dataset['download_status'] = result['status']
                    if result['status'] == 'verified':
                        dataset.update(local_sha256=result['sha256'],
                                       local_bytes=result['bytes'], local_path=result['path'],
                                       md5_verified=True, downloaded_on='2026-11-03')
            manifest['verification_scope'] = (
                'Per-artifact download status, provider MD5 comparison and local SHA-256 '
                'are recorded. See download_status.json; archive inspection is separate.')
            MANIFEST.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    return 1 if any(r['status'] == 'failed' for r in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
