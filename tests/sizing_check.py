"""Actual GTK sizing checks; settings and location are never saved."""
import ctypes as C
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from island.app import Island
from gi.repository import Gtk,Gdk

app=Island(); app.config.data['weather_location']=''; app.config.data['opacity']=1.0; app.config.data['animations']=False
app.register(None); app.activate()
def spin(seconds=.5):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        for _ in range(100):
            if not Gtk.events_pending(): break
            Gtk.main_iteration_do(False)
        time.sleep(.005)
xlib=C.CDLL('libX11.so.6'); xt=C.CDLL('libXtst.so.6')
xlib.XOpenDisplay.argtypes=[C.c_char_p]; xlib.XOpenDisplay.restype=C.c_void_p; d=xlib.XOpenDisplay(None)
xlib.XFlush.argtypes=[C.c_void_p]; xt.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]
xt.XTestFakeMotionEvent(d,-1,10,790,0); xlib.XFlush(d)
spin(); app.expand(False); spin(1)
base=tuple(app.window.get_size()); results=[]
for width,height in [(520,642),(360,400),(320,340),(800,740),(700,380),(340,740)]:
    app.config.data.update(width=width,height=height)
    app.expand(True); spin(.7)
    actual=tuple(app.window.get_size()); pw,ph=app.panel_size()
    check={'requested':[width,height],'actual':actual,'scale':round(app.layout_scale,3),'size_matches':abs(actual[0]-pw)<=2 and abs(actual[1]-ph)<=2}
    # Every section and button must remain within the expanded panel allocation.
    panel=app.panel.get_allocation()
    for key,widget in [('weather',app.weather_card),('apps',app.app_scroll),('audio',app.audio_box),('network',app.netbutton),('bluetooth',app.btbutton)]:
        translated=widget.translate_coordinates(app.panel,0,0)
        allocation=widget.get_allocation()
        check[key]=bool(translated and translated[0]>=0 and translated[1]>=0 and translated[0]+allocation.width<=panel.width+1 and translated[1]+allocation.height<=panel.height+1)
    if (width,height) in [(360,400),(800,740)]:
        x,y=app.window.get_position(); w,h=app.window.get_size()
        Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),x,y,w,h).savev(f'docs/sizing-{width}x{height}.png','png',[],[])
    app.expand(False); spin(.55)
    check['closed_size']=tuple(app.window.get_size()); check['baseline']=base
    check['capsule_unchanged']=tuple(app.window.get_size())==base
    results.append(check); print(check,flush=True)
original=(app.config['width'],app.config['height'])
app.settings(); spin(.2)
assert 'height' in app.settings_fields
app.settings_fields['width'].set_value(400); app.settings_fields['height'].set_value(420); spin(.6)
assert abs(app.window.get_size().width-400)<=2 and abs(app.window.get_size().height-420)<=2
app.settings_window.response(Gtk.ResponseType.CANCEL); spin(.5)
assert (app.config['width'],app.config['height'])==original
print('PASS live settings preview and cancel restore',flush=True)
# Native pointer hit-testing on a resized control (no radio toggle).
app.hold()
app.expand(True); spin(.4)
coords=app.netbutton.translate_coordinates(app.window,0,0)
wx,wy=app.window.get_position(); a=app.netbutton.get_allocation()
xt.XTestFakeMotionEvent(d,-1,wx+coords[0]+a.width//2,wy+coords[1]+a.height//2,0)
xt.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
xt.XTestFakeButtonEvent(d,1,True,0); xt.XTestFakeButtonEvent(d,1,False,0); xlib.XFlush(d); spin(.3)
assert any(p.get_visible() for p in app.popovers)
for p in list(app.popovers): p.popdown()
print('PASS scaled control receives actual mouse click',flush=True)
import tempfile
from island.config import Config
with tempfile.TemporaryDirectory() as folder:
    app.config.path=Path(folder)/'config.json'
    app.settings(); spin(.2)
    app.settings_fields['width'].set_value(420); app.settings_fields['height'].set_value(440)
    app.settings_window.response(Gtk.ResponseType.OK); spin(.5)
    saved=Config(app.config.path)
    assert saved['width']==420 and saved['height']==440
print('PASS width and height saved in temporary XDG-style config',flush=True)
app.shutdown_app()
Path('docs/sizing-results.json').write_text(json.dumps(results,indent=2))
assert all(r['size_matches'] and r['capsule_unchanged'] and all(r[k] for k in ('weather','apps','audio','network','bluetooth')) for r in results)
