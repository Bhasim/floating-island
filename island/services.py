"""System adapters. No desktop settings or credentials are stored here."""
import ctypes as C
import ctypes.util
import json
import os
import subprocess
import threading
import gi
for name, version in [('Gtk','3.0'),('Gdk','3.0'),('Wnck','3.0'),('NM','1.0')]:
    gi.require_version(name, version)
from gi.repository import Gio, GLib, GObject, Wnck, NM


def background(argv, callback=None):
    def work():
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=15)
            result, error = p.stdout, (p.stderr.strip() if p.returncode else '')
        except (OSError, subprocess.TimeoutExpired) as e: result, error = '', str(e)
        if callback: GLib.idle_add(lambda: (callback(result, error), False)[1])
    threading.Thread(target=work, daemon=True).start()


class Service(GObject.Object):
    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_FIRST, None, ())}
    error = ''
    def changed(self, *a): self.emit('changed')


class Windows(Service):
    def __init__(self):
        super().__init__()
        self.handle = Wnck.Handle.new(Wnck.ClientType.PAGER)
        self.screen = self.handle.get_default_screen()
        self.screen.force_update()
        self.handlers = {}
        self.owners = {}
        self.screen_handlers=[]
        for signal in ['window-opened','window-closed','active-window-changed','active-workspace-changed','viewports-changed']:
            self.screen_handlers.append(self.screen.connect(signal, self.refresh))
        self.refresh()

    def refresh(self, *a):
        current = set(self.screen.get_windows())
        for w in list(self.handlers):
            if w not in current:
                for h in self.handlers.pop(w): w.disconnect(h)
        for w in current:
            # libwnck windows keep unowned pointers to their application/class group.
            # Retain their GI wrappers while Python can retain window wrappers.
            group=w.get_class_group(); application=w.get_application()
            if group: self.owners[('group',group.get_id())]=group
            if application: self.owners[('app',application.get_xid())]=application
            if w not in self.handlers:
                self.handlers[w] = [w.connect(s, self.changed) for s in ['name-changed','icon-changed','state-changed','workspace-changed']]
        self.changed()

    def close(self):
        for w, handlers in self.handlers.items():
            for h in handlers: w.disconnect(h)
        self.handlers.clear()
        for h in self.screen_handlers: self.screen.disconnect(h)
        self.screen_handlers.clear()
        self.screen=None

    def items(self, all_workspaces=True):
        space = self.screen.get_active_workspace()
        return [w for w in self.screen.get_windows()
                if not w.is_skip_tasklist() and w.get_pid() != os.getpid()
                and w.get_window_type() in (Wnck.WindowType.NORMAL, Wnck.WindowType.DIALOG)
                and (all_workspaces or w.is_pinned() or w.get_workspace() == space)]

    def activate(self, window, timestamp):
        space = window.get_workspace()
        if space and space != self.screen.get_active_workspace(): space.activate(timestamp)
        if window.is_minimized(): window.unminimize(timestamp)
        window.activate(timestamp)

    def fullscreen(self):
        w = self.screen.get_active_window()
        return bool(w and w.is_fullscreen())


class XkbState(C.Structure):
    _fields_ = [('group',C.c_ubyte),('locked_group',C.c_ubyte),('base_group',C.c_ushort),('latched_group',C.c_ushort),('mods',C.c_ubyte),('base_mods',C.c_ubyte),('latched_mods',C.c_ubyte),('locked_mods',C.c_ubyte),('compat_state',C.c_ubyte),('grab_mods',C.c_ubyte),('compat_grab_mods',C.c_ubyte),('lookup_mods',C.c_ubyte),('compat_lookup_mods',C.c_ubyte),('ptr_buttons',C.c_ushort)]

class XkbEventHeader(C.Structure):
    _fields_=[('type',C.c_int),('serial',C.c_ulong),('send_event',C.c_int),('display',C.c_void_p),('time',C.c_ulong),('subtype',C.c_int),('device',C.c_int)]


class Keyboard(Service):
    def __init__(self):
        super().__init__()
        self.layouts, self.group = [], 0
        self.x = C.CDLL(ctypes.util.find_library('X11'))
        x = self.x
        x.XOpenDisplay.argtypes=[C.c_char_p]; x.XOpenDisplay.restype=C.c_void_p
        self.display=x.XOpenDisplay(None)
        if not self.display: self.error='X11 غير متاح'; return
        for name in ['XkbGetState','XkbLockGroup','XkbSelectEvents','XPending','XNextEvent','XConnectionNumber','XFlush']:
            getattr(x,name).argtypes=[C.c_void_p] + {'XkbGetState':[C.c_uint,C.POINTER(XkbState)], 'XkbLockGroup':[C.c_uint,C.c_uint], 'XkbSelectEvents':[C.c_uint,C.c_uint,C.c_uint], 'XPending':[], 'XNextEvent':[C.c_void_p], 'XConnectionNumber':[], 'XFlush':[]}[name]
        x.XkbSelectEvents(self.display,0x100, (1<<2)|(1<<0), (1<<2)|(1<<0))
        x.XkbSelectEventDetails.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_ulong,C.c_ulong]
        x.XkbSelectEventDetails(self.display,0x100,2,0xffff,(1<<4)|(1<<7))
        x.XFlush(self.display)
        GLib.io_add_watch(x.XConnectionNumber(self.display), GLib.IO_IN, self.event)
        self.read_layouts()
        self.update()

    def read_layouts(self):
        def done(out, err):
            # _XKB_RULES_NAMES has rules, model, layouts, variants, options.
            import re
            values=re.findall(r'"([^"\n]*)"',out)
            self.layouts=values[2].split(',') if len(values)>2 else []
            self.changed()
        background(['xprop','-root','_XKB_RULES_NAMES'],done)

    def event(self,*a):
        event=C.create_string_buffer(192)
        config_changed=False
        while self.x.XPending(self.display):
            self.x.XNextEvent(self.display,event)
            if XkbEventHeader.from_buffer(event).subtype!=2: config_changed=True
        if config_changed: self.read_layouts()
        self.update()
        return True

    def update(self):
        state=XkbState()
        if self.x.XkbGetState(self.display,0x100,C.byref(state))==0:
            self.group=state.group; self.changed()

    @property
    def label(self): return self.layouts[self.group].upper() if self.group<len(self.layouts) else '⌨'

    def next(self):
        if self.layouts:
            self.x.XkbLockGroup(self.display,0x100,(self.group+1)%len(self.layouts)); self.x.XFlush(self.display)


class Audio(Service):
    def __init__(self):
        super().__init__()
        self.volume=0; self.muted=False; self.sinks=[]; self.available=False
        self.running=True; self.pending=False
        self.refresh()
        threading.Thread(target=self.listen,daemon=True).start()

    def listen(self):
        while self.running:
            try:
                self.process=subprocess.Popen(['pactl','subscribe'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
                for line in self.process.stdout:
                    if not self.running: break
                    if any(x in line for x in ['sink','server']): GLib.idle_add(self.schedule)
                self.process.wait()
            except OSError: pass
            if self.running:
                import time
                time.sleep(5)

    def schedule(self):
        if not self.pending:
            self.pending=True
            GLib.timeout_add(90,self.refresh)
        return False

    def refresh(self):
        self.pending=False
        def done(out,err):
            try:
                sinks=json.loads(out); self.sinks=sinks
                # pactl puts the default sink's name in a separate event driven query.
                background(['pactl','get-default-sink'],lambda name,e:self.set_state(sinks,name.strip(),e))
            except (ValueError,TypeError): self.available=False; self.error=err or 'خدمة الصوت غير متاحة'; self.changed()
        background(['pactl','-f','json','list','sinks'],done)
        return False

    def set_state(self,sinks,name,error):
        s=next((s for s in sinks if s['name']==name),None)
        self.available=bool(s)
        if s:
            self.volume=round(sum(v['value'] for v in s['volume'].values())/max(1,len(s['volume']))/65536*100)
            self.muted=s['mute']
        self.changed()

    def set_volume(self,value): background(['pactl','set-sink-volume','@DEFAULT_SINK@',f'{max(0,min(100,round(value)))}%'])
    def toggle(self): background(['pactl','set-sink-mute','@DEFAULT_SINK@','toggle'])
    def output(self,name): background(['pactl','set-default-sink',name])
    def close(self):
        self.running=False
        if getattr(self,'process',None): self.process.terminate()


class Network(Service):
    def __init__(self):
        super().__init__()
        self.client=None; self.wifi=None; self.watched=[]
        try:
            self.client=NM.Client.new(None)
            for s in ['notify::state','notify::wireless-enabled','notify::wireless-hardware-enabled','notify::active-connections','device-added','device-removed']:
                self.client.connect(s,self.refresh)
            self.refresh()
        except GLib.Error: self.error='NetworkManager غير متاح'

    def refresh(self,*a):
        for obj,h in self.watched: GObject.signal_handler_disconnect(obj,h)
        self.watched=[]
        if self.client:
            self.wifi=next((d for d in self.client.get_devices() if isinstance(d,NM.DeviceWifi)),None)
            for device in self.client.get_devices():
                self.watched.append((device,device.connect('notify::state',self.refresh)))
            if self.wifi:
                for sig in ['notify::active-access-point','access-point-added','access-point-removed']:
                    self.watched.append((self.wifi,self.wifi.connect(sig,self.refresh)))
                ap=self.wifi.get_active_access_point()
                if ap: self.watched.append((ap,ap.connect('notify::strength',self.changed)))
        self.changed()

    @staticmethod
    def ssid(ap):
        value=ap.get_ssid()
        return NM.utils_ssid_to_utf8(value.get_data()) if value else 'شبكة مخفية'

    @property
    def label(self):
        if not self.client or not self.client.get_nm_running(): return 'الشبكة غير متاحة'
        if self.wifi and not self.client.wireless_hardware_get_enabled(): return 'Wi-Fi محظور عتاديًا'
        if self.wifi and not self.client.wireless_get_enabled(): return 'Wi-Fi متوقف'
        if self.wifi and self.wifi.get_active_access_point():
            ap=self.wifi.get_active_access_point()
            return f'{self.ssid(ap)} · {ap.get_strength()}%'
        if any(d.get_device_type()==NM.DeviceType.ETHERNET and d.get_state()==NM.DeviceState.ACTIVATED for d in self.client.get_devices()): return 'Ethernet متصل'
        return 'غير متصل'

    def toggle(self):
        if self.client and self.wifi: self.client.wireless_set_enabled(not self.client.wireless_get_enabled())

    def scan(self):
        if self.wifi:
            self.wifi.request_scan_async(None,lambda obj,res:self.scan_done(obj,res))

    def scan_done(self,obj,res):
        try: obj.request_scan_finish(res)
        except GLib.Error: pass
        self.changed()

    def access_points(self):
        if not self.wifi: return []
        seen={}
        for ap in self.wifi.get_access_points():
            ssid=self.ssid(ap)
            if ssid not in seen or ap.get_strength()>seen[ssid].get_strength(): seen[ssid]=ap
        return sorted(seen.values(),key=lambda a:-a.get_strength())


class Bluez(Service):
    def __init__(self):
        super().__init__()
        self.manager=None
        try:
            self.manager=Gio.DBusObjectManagerClient.new_for_bus_sync(Gio.BusType.SYSTEM,Gio.DBusObjectManagerClientFlags.NONE,'org.bluez','/',None,None,None)
            for signal in ['object-added','object-removed','interface-proxy-properties-changed']: self.manager.connect(signal,self.changed)
        except GLib.Error: self.error='Bluetooth غير متاح'

    def interfaces(self,name):
        return [i for o in self.manager.get_objects() for i in o.get_interfaces() if i.get_interface_name()==name] if self.manager else []
    @property
    def adapters(self): return self.interfaces('org.bluez.Adapter1')
    @staticmethod
    def prop(proxy,name,default=None):
        v=proxy.get_cached_property(name)
        return v.unpack() if v else default
    def call(self,proxy,method,args=None):
        def done(obj,res):
            try: obj.call_finish(res); self.error=''
            except GLib.Error as e: self.error=e.message
            self.changed()
        proxy.call(method,args,Gio.DBusCallFlags.NONE,15000,None,done)
    def toggle(self):
        if self.adapters:
            a=self.adapters[0]
            self.call(a,'org.freedesktop.DBus.Properties.Set',GLib.Variant('(ssv)',('org.bluez.Adapter1','Powered',GLib.Variant('b',not self.prop(a,'Powered',False)))))


class Battery(Service):
    def __init__(self):
        super().__init__()
        self.proxy=None
        self.connect_proxy()
    def connect_proxy(self):
        try:
            self.proxy=Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM,Gio.DBusProxyFlags.NONE,None,'org.freedesktop.UPower','/org/freedesktop/UPower/devices/DisplayDevice','org.freedesktop.UPower.Device',None)
            self.proxy.connect('g-properties-changed',self.changed)
        except GLib.Error: pass
    def prop(self,key,default=None):
        v=self.proxy.get_cached_property(key) if self.proxy else None
        return v.unpack() if v else default
    @property
    def present(self): return self.prop('IsPresent',False) and self.prop('Type',0)==2
    @property
    def label(self):
        if not self.present: return ''
        state=self.prop('State',0)
        text=f"{self.prop('Percentage',0):.0f}%" + (' ⚡' if state==1 else '')
        seconds=self.prop('TimeToFull' if state==1 else 'TimeToEmpty',0)
        if 60<=seconds<=7*86400: text+=f' · {seconds//3600}:{seconds%3600//60:02d}'
        return text
