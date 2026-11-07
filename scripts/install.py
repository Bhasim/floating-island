#!/usr/bin/python3
"""User-only installation. Does not enable autostart or change Xfce."""
import os
from pathlib import Path
import shlex
import shutil

source=Path(__file__).resolve().parents[1]
data=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'floating-island'
binpath=Path.home()/'.local/bin/floating-island'
if source == data:
    raise SystemExit('Already running from the installation directory.')
data.mkdir(parents=True,exist_ok=True)
shutil.copytree(source/'island',data/'island',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
for name in ['README.md','LICENSE','requirements-system.txt']:
    shutil.copy2(source/name,data/name)
shutil.copytree(source/'scripts',data/'scripts',dirs_exist_ok=True)
binpath.parent.mkdir(parents=True,exist_ok=True)
binpath.write_text('#!/bin/sh\ncd -- '+shlex.quote(str(data))+'\nexec /usr/bin/python3 -m island.app "$@"\n')
binpath.chmod(0o755)
apps=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'applications'
apps.mkdir(parents=True,exist_ok=True)
# Desktop Entry Exec has its own quoting rules, independent of shell escaping.
exe=str(binpath).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
(apps/'floating-island.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Floating Island\nName[ar]=الجزيرة العائمة\nComment=Lightweight X11 desktop controls\nExec="{exe}"\nIcon=view-grid-symbolic\nTerminal=false\nCategories=Utility;\nStartupNotify=false\n')
print('Installed:',binpath)
print('Autostart remains disabled.')
