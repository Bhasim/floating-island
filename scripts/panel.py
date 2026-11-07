#!/usr/bin/python3
"""Read-only panel backup, or ensure the existing panel is running."""
from pathlib import Path
from datetime import datetime
import os
import shutil
import subprocess
import sys
if sys.argv[1:] == ['backup']:
    root=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'floating-island'
    target=root/('panel-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    target.mkdir(parents=True,mode=0o700)
    cfg=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'xfce4'
    for rel in ['panel','xfconf/xfce-perchannel-xml/xfce4-panel.xml']:
        p=cfg/rel
        if p.is_dir(): shutil.copytree(p,target/'panel')
        elif p.exists(): shutil.copy2(p,target/p.name)
    dump=subprocess.run(['xfconf-query','-c','xfce4-panel','-lv'],capture_output=True,text=True)
    (target/'properties.txt').write_text(dump.stdout)
    print(target)
elif sys.argv[1:] == ['ensure-running']:
    # No stop, hide, reset, or reload operation is performed.
    if subprocess.run(['pgrep','-u',str(os.getuid()),'-x','xfce4-panel'],stdout=subprocess.DEVNULL).returncode:
        subprocess.Popen(['xfce4-panel'],start_new_session=True)
    print('Panel is running; its configuration was not changed.')
else: raise SystemExit('Usage: panel.py backup|ensure-running')
