#!/usr/bin/python3
"""Capture real GTK UI with demonstration data, never account configuration."""
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import PropertyMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from island.app import Island
from gi.repository import Gdk, Gtk

app=Island()
app.config.data.update(weather_location='',opacity=1.0,animations=False,show_network=True,show_bluetooth=True,show_audio=True,show_keyboard=True)
app.register(None); app.activate()

def spin(seconds=.4):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        for _ in range(100):
            if not Gtk.events_pending(): break
            Gtk.main_iteration_do(False)
        time.sleep(.005)

def shot(name):
    x,y=app.window.get_position();w,h=app.window.get_size()
    Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),x,y,w,h).savev(str(Path('docs')/name),'png',[],[])

child=subprocess.Popen(['/usr/bin/python3','-c',"""
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
windows=[]
for name,icon in [('Editor','accessories-text-editor'),('Terminal','utilities-terminal'),('Browser','web-browser')]:
 w=Gtk.Window(title='Island Demo '+name); w.set_icon_name(icon); w.add(Gtk.Label(label='Public demonstration window')); w.show_all(); windows.append(w)
Gtk.main()
"""])
try:
    original_items=app.windows.items
    app.windows.items=lambda all_workspaces=True:[w for w in original_items(all_workspaces) if w.get_name().startswith('Island Demo ')]
    with patch.object(type(app.network),'label',new_callable=PropertyMock,return_value='شبكة تجريبية'),patch.object(type(app.keyboard),'label',new_callable=PropertyMock,return_value='EN'):
        spin(.7);app.audio.volume=30;app.audio.muted=False;app.update();app.window_changed();app.hold()
        for width,height,name in [(520,642,'expanded.png'),(360,400,'sizing-360x400.png'),(800,740,'sizing-800x740.png')]:
            app.config.data.update(width=width,height=height);app.expand(True);spin(.5);shot(name)
        app.release();app.expand(False);spin(.5);shot('collapsed.png')
finally:
    child.terminate();child.wait();spin(.2);app.shutdown_app()
