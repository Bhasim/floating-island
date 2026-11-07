import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
class PackagingTests(unittest.TestCase):
    def test_install_autostart_remove_are_user_scoped(self):
        with tempfile.TemporaryDirectory(prefix='island package ') as folder:
            home=Path(folder)/'home'; home.mkdir()
            env={'XDG_DATA_HOME':str(home/'data with spaces'),'XDG_CONFIG_HOME':str(home/'config')}
            with patch.dict(os.environ,env),patch.object(Path,'home',return_value=home):
                runpy.run_path(str(ROOT/'scripts/install.py'),run_name='__main__')
                self.assertTrue((home/'.local/bin/floating-island').exists())
                self.assertFalse((home/'config/autostart/floating-island.desktop').exists())
                with patch('sys.argv',['autostart.py','enable']): runpy.run_path(str(ROOT/'scripts/autostart.py'))
                self.assertTrue((home/'config/autostart/floating-island.desktop').exists())
                with patch('sys.argv',['autostart.py','disable']): runpy.run_path(str(ROOT/'scripts/autostart.py'))
                with patch('subprocess.run'):
                    runpy.run_path(str(ROOT/'scripts/uninstall.py'))
                self.assertFalse((home/'.local/bin/floating-island').exists())
                self.assertFalse((home/'data with spaces/floating-island').exists())
