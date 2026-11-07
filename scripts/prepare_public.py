#!/usr/bin/python3
"""Build a reviewed source-only release; never copy account or Git metadata."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

root=Path(__file__).resolve().parents[1]
destination=root/'public-release'
fixed=['.gitignore','README.md','LICENSE','SECURITY.md','requirements-system.txt','run.sh']
files=[root/p for p in fixed]
for folder in ['island','scripts','tests']:
    files+=sorted((root/folder).glob('*.py'))+sorted((root/folder).glob('*.md'))
files+=sorted((root/'docs').glob('*.md'))
files += [root/'docs'/name for name in ['performance.json','ui-results.json','sizing-results.json','collapsed.png','expanded.png','sizing-360x400.png','sizing-800x740.png']]
patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'\bgh[pousr]_[A-Za-z0-9]{20,}\b',r'\bgithub_pat_[A-Za-z0-9_]{20,}\b',r'\bsk-[A-Za-z0-9]{20,}\b',r'\b(?:[a-fA-F0-9]{2}:){5}[a-fA-F0-9]{2}\b',r'/' + r'home/[^/\s]+/']
manifest=[]
for path in files:
    if path.is_symlink(): raise SystemExit('Refusing a symlink: '+str(path.relative_to(root)))
    raw=path.read_bytes()
    if path.suffix!='.png':
        text=raw.decode('utf-8')
        if any(re.search(pattern,text) for pattern in patterns):
            raise SystemExit('Review possible private data in '+str(path.relative_to(root)))
    manifest.append({'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
if destination.exists(): shutil.rmtree(destination)
destination.mkdir()
for path in files:
    target=destination/path.relative_to(root)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(path,target)
(destination/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
archive=root/'dist/floating-island-0.4.0.zip'
archive.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted(destination.rglob('*')):
        if path.is_file(): z.write(path,'floating-island/'+path.relative_to(destination).as_posix())
print('Reviewed files:',len(manifest))
print('Public tree: public-release/')
print('Archive: dist/'+archive.name)
