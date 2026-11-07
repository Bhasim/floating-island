import json
import os
from pathlib import Path

DEFAULTS = dict(monitor=0, top=6, offset=0, width=520, height=642, opacity=0.96,
                color='#171b26', animations=True, open_delay=220,
                close_delay=650, hide_fullscreen=True, all_workspaces=True,
                show_keyboard=True, show_audio=True, show_network=True,
                show_bluetooth=True, show_battery=True, weather_location='')

class Config:
    def __init__(self, path=None):
        self.path = Path(path or Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'floating-island'/'config.json')
        self.data = DEFAULTS.copy()
        self.warning = ''
        try:
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict):
                raise ValueError('expected object')
            for k, default in DEFAULTS.items():
                value = raw.get(k, default)
                if type(value) is type(default): self.data[k] = value
        except FileNotFoundError: pass
        except (ValueError, OSError): self.warning = 'تعذرت قراءة الإعدادات؛ استُخدمت القيم الافتراضية.'
        for k, lo, hi in [('monitor',0,32),('top',0,400),('offset',-4000,4000),('width',320,1600),('height',340,1400),('open_delay',0,3000),('close_delay',100,5000),('opacity',0.3,1.0)]:
            self.data[k] = max(lo, min(hi, self.data[k]))
        import re
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', self.data['color']): self.data['color'] = DEFAULTS['color']

    def __getitem__(self, key): return self.data[key]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            os.chmod(tmp, 0o600)
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)
