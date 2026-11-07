import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from island.config import Config
from island.weather import Weather, condition, location, parse_forecast
from gi.repository import GLib

FORECAST={'current':{'temperature_2m':12.3,'weather_code':63,'is_day':1,'time':'2026-11-07T12:00'},'daily':{'temperature_2m_max':[14.1],'temperature_2m_min':[7.4],'time':['2026-11-07']}}

def wait_for(predicate):
    until=time.monotonic()+2
    while not predicate() and time.monotonic()<until:
        while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
        time.sleep(.005)
    if not predicate(): raise AssertionError('Async callback did not complete')

class WeatherTests(unittest.TestCase):
    def test_codes_and_real_daily_range(self):
        for code,word in [(0,'صافٍ'),(3,'غائم'),(45,'ضباب'),(63,'ممطر'),(75,'ثلوج'),(95,'عواصف رعدية')]:
            self.assertEqual(condition(code)[1],word)
        self.assertEqual(parse_forecast(FORECAST)['high'],14.1)
        self.assertEqual(parse_forecast(FORECAST)['low'],7.4)
        with self.assertRaises(ValueError): location('test',float('nan'),0)
        with self.assertRaises(ValueError): location('test',91,0)

    def test_opt_in_cache_failure_and_private_storage(self):
        with tempfile.TemporaryDirectory() as d,patch('island.weather.get_json',return_value=FORECAST) as http:
            config=Config(Path(d)/'private/config.json'); weather=Weather(config)
            weather.refresh(); http.assert_not_called()
            weather.set_location(location('مدينة اختبار',0,0))
            wait_for(lambda:not weather.loading)
            self.assertEqual(weather.data['temperature'],12.3)
            self.assertEqual(http.call_count,1)
            weather.refresh(); self.assertEqual(http.call_count,1)
            self.assertIn('مدينة اختبار',config.path.read_text())
            self.assertEqual(config.path.stat().st_mode & 0o777,0o600)
            weather.last_attempt=float('-inf'); http.side_effect=OSError('network failure')
            weather.refresh(); wait_for(lambda:not weather.loading)
            self.assertTrue(weather.error)
            self.assertEqual(weather.data['temperature'],12.3)
            weather.clear_location(); self.assertIsNone(weather.place); self.assertIsNone(weather.data)
            self.assertEqual(json.loads(config.path.read_text())['weather_location'],'')

    def test_location_requires_explicit_resolution_and_drops_ip(self):
        with tempfile.TemporaryDirectory() as d,patch('island.weather.get_json',return_value=dict(success=True,city='Test',country='Testland',latitude=0,longitude=0,ip='PRIVATE')) as http:
            weather=Weather(Config(Path(d)/'config.json'))
            http.assert_not_called(); responses=[]
            weather.resolve('',True,lambda places,error:responses.append((places,error)))
            wait_for(lambda:bool(responses))
            result,error=responses[0]
            self.assertFalse(error); self.assertEqual(result[0]['latitude'],0)
            self.assertNotIn('ip',result[0]); self.assertIsNone(weather.place)
            self.assertFalse(weather.config.path.exists())
