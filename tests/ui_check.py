"""Real X11/GTK smoke checks; never toggles network radios or sound."""
import ctypes as C
import ctypes.util
import json
import time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from island.app import Island
gi_unused = None
from gi.repository import Gtk, Gdk, GLib, Wnck
import gi
gi.require_version('GdkX11','3.0')
from gi.repository import GdkX11

app=Island(); app.config.data['weather_location']=''; app.config.data['opacity']=1.0; app.register(None); app.activate()

def spin(seconds=0.3):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        time.sleep(.005)

x=C.CDLL(ctypes.util.find_library('X11')); xt=C.CDLL(ctypes.util.find_library('Xtst'))
x.XOpenDisplay.restype=C.c_void_p; x.XOpenDisplay.argtypes=[C.c_char_p]; d=x.XOpenDisplay(None)
x.XFlush.argtypes=[C.c_void_p]
xt.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]
def move(px,py): xt.XTestFakeMotionEvent(d,-1,px,py,0); x.XFlush(d); spin(.4)

def shot(name):
    w=app.window; px,py=w.get_position(); width,height=w.get_size()
    root=Gdk.get_default_root_window()
    Gdk.pixbuf_get_from_window(root,px,py,width,height).savev(str(Path('docs')/name),'png',[],[])

results=[]
def check(condition,text):
    results.append({'test':text,'passed':bool(condition)})
    print(('PASS ' if condition else 'FAIL ')+text,flush=True)

spin(1)
original=app.windows.screen.get_active_window()
move(20,500); app.expand(False); spin(.5)
print('sizes',app.window.get_size(),app.cap.get_allocation().width,app.summary.get_allocation().width,flush=True)
shot('collapsed.png')
check(not app.registration_label.get_mapped(),'Registration hidden while collapsed')
check(not app.weather_card.get_mapped(),'Weather card hidden while collapsed')
check(not app.clock_label.get_mapped(),'Clock hidden while collapsed')
check(app.clock_timer==0 and app.weather_timer==0,'No clock or weather timer while collapsed')
active=app.windows.screen.get_active_window()
px,py=app.window.get_position(); move(px+25,py+15)
check(app.expanded,'Pointer hover opens island')
check(app.windows.screen.get_active_window()==active,'Hover preserves active window')
spin(.3)
check(app.registration_label.get_mapped() and app.registration_label.get_text()=='Register Bahaalden Hashim','Registration visible in expanded footer')
check(app.weather_card.get_mapped() and app.clock_label.get_mapped(),'Clock and weather visible only in expanded panel')
check(':' in app.clock_label.get_text() and '\n' in app.date_label.get_text(),'Clock, weekday and full date rendered')
from unittest.mock import patch
with patch.object(app.bluez,'prop',return_value=False):
    app.update()
    check('متوقف' in app.btbutton.get_label() and app.btbutton.get_style_context().has_class('bluetooth-off'),'Bluetooth off state has text and gray style')
with patch.object(app.bluez,'prop',return_value=True):
    app.update()
    check('مفعّل' in app.btbutton.get_label() and app.btbutton.get_style_context().has_class('bluetooth-on'),'Bluetooth on state has text and blue style')
app.update()
from island.weather import parse_forecast
app.weather.data=parse_forecast({'current':{'temperature_2m':12,'weather_code':63,'time':'test'},'daily':{'temperature_2m_max':[15],'temperature_2m_min':[8],'time':['test']}})
app.update_weather()
check('15' in app.weather_range.get_text() and '8' in app.weather_range.get_text() and app.weather_description.get_text()=='ممطر','Weather card renders condition and both daily extremes')
app.weather.data=None; app.update_weather(); spin(.2)
shot('expanded.png')
px,py=app.window.get_position(); move(px+80,py+100); spin(.8)
check(app.expanded,'Moving into panel keeps it open')
app.hold(); move(20,500); spin(1)
check(app.expanded,'Drag/child hold prevents collapse')
app.release(); spin(1)
check(not app.expanded,'Leaving closes after delay')
for i in range(12): app.expand(True); spin(.18); app.expand(False); spin(.18)
check(not app.expanded,'12 repeated expand/collapse cycles')
# Create windows owned by a different PID so production filtering remains enabled.
import subprocess
child=subprocess.Popen(['/usr/bin/python3','-c',"import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk; w=Gtk.Window(title='Island integration window'); w.set_default_size(320,180); w.show_all(); Gtk.main()"])
try:
    spin(1); app.windows.screen.force_update(); items=app.windows.items()
    target=next((w for w in items if w.get_name()=='Island integration window'),None)
    check(target is not None,'External window appears in EWMH list')
    if target:
        target.minimize(); spin(.4)
        ts=GdkX11.x11_get_server_time(app.window.get_window())
        app.windows.activate(target,ts); spin(.6)
        check(not target.is_minimized() and target.is_active(),'Activate restores minimized window')
        previous=app.windows.screen.get_active_workspace()
        other=next((w for w in app.windows.screen.get_workspaces() if w!=previous),None)
        if other:
            target.move_to_workspace(other); spin(.4)
            check(target not in app.windows.items(False),'Current-workspace filter excludes other workspace')
            app.windows.activate(target,GdkX11.x11_get_server_time(app.window.get_window())); spin(.7)
            check(app.windows.screen.get_active_workspace()==other and target.is_active(),'Activation switches workspace')
            target.move_to_workspace(previous); previous.activate(GdkX11.x11_get_server_time(app.window.get_window())); spin(.4)
        target.set_fullscreen(True); app.windows.activate(target,GdkX11.x11_get_server_time(app.window.get_window())); spin(.7)
        check(not app.window.get_visible(),'Fullscreen hides island')
        target.set_fullscreen(False); spin(.5)
        check(app.window.get_visible(),'Leaving fullscreen restores island')
finally:
    child.terminate(); child.wait(); spin(.5)
    if original: app.windows.activate(original,GdkX11.x11_get_server_time(app.window.get_window()))
check(all(w.get_pid()!=__import__('os').getpid() for w in app.windows.items()),'Island excluded from window list')
# Region corners do not capture pointer events.
check(app.window.get_window().get_type_hint()==Gdk.WindowTypeHint.DOCK,'Dock window hint')
check(not app.window.get_accept_focus(),'Main window refuses keyboard focus')
check(bool(app.keyboard.layouts),'Real keyboard layouts detected')
check(app.audio.available,'PulseAudio-compatible output detected')
check(app.network.client is not None,'NetworkManager available')

# Verify rounded transparent corner click-through using X11's pointer child.
x.XQueryPointer.argtypes=[C.c_void_p,C.c_ulong]+[C.c_void_p]*7
x.XDefaultRootWindow.argtypes=[C.c_void_p]; x.XDefaultRootWindow.restype=C.c_ulong
root=x.XDefaultRootWindow(d)
def pointer_child():
    rr=C.c_ulong(); child=C.c_ulong(); rx=C.c_int(); ry=C.c_int(); wx=C.c_int(); wy=C.c_int(); mask=C.c_uint()
    x.XQueryPointer(d,root,C.byref(rr),C.byref(child),C.byref(rx),C.byref(ry),C.byref(wx),C.byref(wy),C.byref(mask))
    return child.value
app.expand(False); spin(.4); px,py=app.window.get_position()
move(px+1,py+1)
check(pointer_child()!=app.window.get_window().get_xid(),'Transparent corner passes pointer through')
move(px+30,py+18)
x.XQueryTree.argtypes=[C.c_void_p,C.c_ulong,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
rr=C.c_ulong(); parent=C.c_ulong(); children=C.c_void_p(); count=C.c_uint()
x.XQueryTree(d,app.window.get_window().get_xid(),C.byref(rr),C.byref(parent),C.byref(children),C.byref(count))
x.XFree.argtypes=[C.c_void_p]
if children: x.XFree(children)
check(pointer_child() in (app.window.get_window().get_xid(),parent.value),'Capsule center receives pointer')
# External XKB lock change must be reflected without rebuilding shortcuts.
if len(app.keyboard.layouts)>1:
    saved=app.keyboard.group
    x.XkbLockGroup.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
    x.XkbLockGroup(d,0x100,(saved+1)%len(app.keyboard.layouts)); x.XFlush(d); spin(.4)
    check(app.keyboard.group==(saved+1)%len(app.keyboard.layouts),'External XKB change updates indicator')
    x.XkbLockGroup(d,0x100,saved); x.XFlush(d); spin(.4)
    check(app.keyboard.group==saved,'Original keyboard group restored')
app.settings(); spin(.4)
check(app.settings_window is not None and app.settings_window.get_visible(),'Settings opens a real separate window')
x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong]; x.XKeysymToKeycode.restype=C.c_ubyte
xt.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
code=x.XKeysymToKeycode(d,0xff1b)
xt.XTestFakeKeyEvent(d,code,True,0); xt.XTestFakeKeyEvent(d,code,False,0); x.XFlush(d); spin(.4)
check(app.settings_window is None,'Escape closes focused settings')

with patch('island.weather.get_json') as http:
    app.choose_location(); spin(.2)
    check(app.location_dialog is not None,'Location chooser opens inside application')
    http.assert_not_called()
    chooser=app.location_dialog
    auto=next(w for w in chooser.get_content_area().get_children() if isinstance(w,Gtk.Button) and 'تلقائي' in (w.get_label() or ''))
    def deny_location():
        for w in Gtk.Window.list_toplevels():
            if isinstance(w,Gtk.MessageDialog): w.response(Gtk.ResponseType.CANCEL)
        return False
    GLib.timeout_add(100,deny_location)
    auto.emit('clicked'); spin(.2)
    check(http.call_count==0 and app.weather.place is None,'Denying location consent sends no request and saves no city')
    chooser.response(Gtk.ResponseType.CLOSE); spin(.2)
app.output_menu(); spin(.2)
check(bool(app.popovers),'Audio output menu opens')
for p in list(app.popovers): p.popdown()
app.network_menu(); spin(.2)
check(bool(app.popovers),'Network menu opens without changing connection')
for p in list(app.popovers): p.popdown()
app.bluetooth_menu(); spin(.2)
check(bool(app.popovers),'Bluetooth menu opens without toggling radio')
for p in list(app.popovers): p.popdown()
spin(.2)
Path('docs/ui-results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
target=None; original=None; active=None; items=[]; win=None; previous=None; other=None
app.shutdown_app()
sys.exit(0 if all(r['passed'] for r in results) else 1)
