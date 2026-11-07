"""Opt-in location and weather. No location requests until user action."""
import json
import math
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .services import Service, GLib


def get_json(url):
    request = Request(url, headers={'User-Agent': 'FloatingIsland/0.2'})
    with urlopen(request, timeout=12) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Response too large')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Invalid response')
    return value


def location(city, latitude, longitude):
    lat, lon = float(latitude), float(longitude)
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Invalid location')
    return {'city': str(city)[:160], 'latitude': lat, 'longitude': lon}


def condition(code, daytime=True):
    if code == 0: return ('weather-clear-symbolic' if daytime else 'weather-clear-night-symbolic', 'صافٍ')
    if code in (1, 2): return ('weather-few-clouds-symbolic', 'غائم جزئيًا')
    if code == 3: return ('weather-overcast-symbolic', 'غائم')
    if code in (45, 48): return ('weather-fog-symbolic', 'ضباب')
    if code in (51, 53, 55, 56, 57): return ('weather-showers-scattered-symbolic', 'رذاذ')
    if code in (61, 63, 65, 66, 67, 80, 81, 82): return ('weather-showers-symbolic', 'ممطر')
    if code in (71, 73, 75, 77, 85, 86): return ('weather-snow-symbolic', 'ثلوج')
    if code in (95, 96, 99): return ('weather-storm-symbolic', 'عواصف رعدية')
    return ('weather-severe-alert-symbolic', 'حالة غير معروفة')


def parse_forecast(raw):
    current, daily = raw['current'], raw['daily']
    values = [float(current['temperature_2m']), float(daily['temperature_2m_max'][0]), float(daily['temperature_2m_min'][0])]
    if not all(math.isfinite(v) for v in values): raise ValueError('Invalid temperature')
    icon, description = condition(int(current['weather_code']), bool(current.get('is_day', 1)))
    return dict(temperature=values[0], high=values[1], low=values[2], icon=icon,
                description=description, time=str(current['time']), date=str(daily['time'][0]))


class Weather(Service):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.data = None
        self.error = ''
        self.loading = False
        self.last_attempt = float('-inf')
        self.generation = 0
        self.location_busy = False

    @property
    def place(self):
        try:
            value = json.loads(self.config['weather_location'])
            return location(value['city'], value['latitude'], value['longitude'])
        except (ValueError, TypeError, KeyError): return None

    def set_location(self, place):
        value = location(place['city'], place['latitude'], place['longitude'])
        # Only XDG user settings are written; never source files or logs.
        previous = self.config.data['weather_location']
        self.config.data['weather_location'] = json.dumps(value, ensure_ascii=False)
        try: self.config.save()
        except OSError:
            self.config.data['weather_location'] = previous
            raise
        self.generation += 1
        self.data = None; self.loading = False; self.last_attempt = float('-inf'); self.error = ''
        self.changed()
        self.refresh()

    def clear_location(self):
        previous = self.config.data['weather_location']
        self.config.data['weather_location'] = ''
        try: self.config.save()
        except OSError:
            self.config.data['weather_location'] = previous
            raise
        self.generation += 1
        self.data = None; self.loading = False; self.error = ''; self.last_attempt = float('-inf')
        self.changed()

    def resolve(self, query, automatic, callback):
        """Called only after explicit manual search or IP-location consent."""
        if self.location_busy:
            callback([], 'انتظر انتهاء طلب الموقع السابق ثم حاول مجددًا.'); return
        self.location_busy = True
        def work():
            result, error = [], ''
            try:
                if automatic:
                    raw = get_json('https://ipwho.is/?fields=success,city,country,latitude,longitude')
                    if not raw.get('success'): raise ValueError('Location unavailable')
                    result = [location('، '.join(filter(None, [raw.get('city'), raw.get('country')])), raw['latitude'], raw['longitude'])]
                else:
                    raw = get_json('https://geocoding-api.open-meteo.com/v1/search?' + urlencode(dict(name=query, count=5, language='ar', format='json')))
                    result = [location('، '.join(dict.fromkeys(filter(None, [p.get('name'), p.get('admin1'), p.get('country')]))), p['latitude'], p['longitude']) for p in raw.get('results', [])]
                if not result: error = 'لم يُعثر على مدينة؛ جرّب اسمها بلغة أخرى.'
            except Exception:
                error = 'تعذر تحديد الموقع. تحقّق من الإنترنت أو أدخل المدينة يدويًا.'
            def finish():
                self.location_busy = False
                callback(result, error)
                return False
            GLib.idle_add(finish)
        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        place = self.place
        if not place or self.loading or time.monotonic() - self.last_attempt < 900: return
        self.last_attempt = time.monotonic(); self.loading = True; self.error = ''
        generation = self.generation
        self.changed()
        def work():
            data, error = None, ''
            try:
                query = urlencode(dict(latitude=place['latitude'], longitude=place['longitude'], current='temperature_2m,weather_code,is_day', daily='temperature_2m_max,temperature_2m_min', timezone='auto', forecast_days=1))
                data = parse_forecast(get_json('https://api.open-meteo.com/v1/forecast?' + query))
            except Exception:
                error = 'تعذر تحديث الطقس؛ تحقّق من اتصال الإنترنت.'
            def finish():
                if generation != self.generation: return False
                self.loading = False; self.error = error
                if data: self.data = data
                self.changed()
                return False
            GLib.idle_add(finish)
        threading.Thread(target=work, daemon=True).start()
