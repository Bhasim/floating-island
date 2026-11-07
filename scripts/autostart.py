#!/usr/bin/python3
import os
from pathlib import Path
import shutil
import sys
config=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'autostart/floating-island.desktop'
source=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'applications/floating-island.desktop'
if sys.argv[1:] == ['enable']:
    if not source.exists(): raise SystemExit('Install the application first.')
    config.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,config)
    print('Autostart enabled.')
elif sys.argv[1:] == ['disable']:
    config.unlink(missing_ok=True); print('Autostart disabled.')
else: raise SystemExit('Usage: autostart.py enable|disable')
