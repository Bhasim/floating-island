#!/usr/bin/python3
import os
from pathlib import Path
import shutil
import subprocess
launcher=Path.home()/'.local/bin/floating-island'
if launcher.exists(): subprocess.run([str(launcher),'--quit'],check=False)
data=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
config=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
for p in [launcher,data/'applications/floating-island.desktop',config/'autostart/floating-island.desktop']:
    p.unlink(missing_ok=True)
shutil.rmtree(data/'floating-island',ignore_errors=True)
print('Removed. Your settings remain in',config/'floating-island')
