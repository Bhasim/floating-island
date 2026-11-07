import json
import tempfile
import unittest
from pathlib import Path
from island.config import Config

class ConfigTests(unittest.TestCase):
    def test_corrupt_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'; p.write_text('{broken')
            c=Config(p); self.assertTrue(c.warning)
            p.write_text(json.dumps({'width':90000,'height':-200,'opacity':-1.0,'color':'invalid','show_audio':'yes','monitor':-1}))
            c=Config(p)
            self.assertEqual(c['width'],1600); self.assertEqual(c['height'],340); self.assertEqual(c['opacity'],0.3)
            self.assertEqual(c['color'],'#171b26'); self.assertIs(c['show_audio'],True)
            self.assertEqual(c['monitor'],0)
            c.save(); self.assertEqual(Config(p).data,c.data)
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
    def test_non_object(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'; p.write_text('[]')
            self.assertTrue(Config(p).warning)

if __name__=='__main__': unittest.main()
