from datetime import datetime
import math
import os
import signal
import subprocess
import sys
from pathlib import Path
import cairo
import gi
gi.require_version('Gtk','3.0')
gi.require_version('Gdk','3.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Pango
from .layout import panel_metrics
from .weather import Weather
from .config import Config
from .services import Windows, Keyboard, Audio, Network, Bluez, Battery, background


def button(label=None, icon=None, callback=None):
    b=Gtk.Button(label=label) if label else Gtk.Button()
    if icon: b.set_image(Gtk.Image.new_from_icon_name(icon,Gtk.IconSize.BUTTON))
    b.set_relief(Gtk.ReliefStyle.NONE)
    b.set_can_focus(False)
    if callback: b.connect('clicked',lambda *_:callback())
    return b


def label(text):
    w=Gtk.Label(label=text); w.set_xalign(0)
    w.set_ellipsize(Pango.EllipsizeMode.END)
    return w


class Island(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.floatingisland.Desktop',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.config=Config(); self.window=None
        self.connect('activate',self.activate_app)
        self.connect('command-line',self.command_line)
        self.connect('shutdown',self.shutdown_app)

    def command_line(self,app,cmd):
        args=cmd.get_arguments()[1:]
        if '--quit' in args: self.quit(); return 0
        self.activate()
        if '--settings' in args: self.settings()
        elif '--expand' in args: self.expand(True)
        elif '--collapse' in args: self.expand(False)
        return 0

    def activate_app(self,*_):
        if self.window: return
        self.windows=Windows(); self.keyboard=Keyboard(); self.audio=Audio()
        self.network=Network(); self.bluez=Bluez(); self.battery=Battery()
        self.weather=Weather(self.config); self.clock_timer=0; self.weather_timer=0; self.location_dialog=None
        self.expanded=False; self.open_timer=0; self.close_timer=0; self.busy=0
        self.popovers=[]; self.settings_window=None; self.audio_sync=False
        self.window=Gtk.ApplicationWindow(application=self,title='Floating Island')
        w=self.window
        w.set_name('island'); w.set_decorated(False); w.set_resizable(False)
        w.set_skip_taskbar_hint(True); w.set_skip_pager_hint(True)
        w.set_type_hint(Gdk.WindowTypeHint.DOCK); w.set_keep_above(True)
        w.stick(); w.set_accept_focus(False); w.set_focus_on_map(False)
        visual=w.get_screen().get_rgba_visual()
        if visual: w.set_visual(visual)
        w.set_app_paintable(True)
        w.connect('draw',self.draw_background)
        w.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK|Gdk.EventMask.LEAVE_NOTIFY_MASK)
        w.connect('enter-notify-event',self.enter)
        w.connect('leave-notify-event',self.leave)
        w.connect('key-press-event',self.key)
        w.connect('size-allocate',self.allocated)
        self.outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0)
        w.add(self.outer)
        self.cap=Gtk.Box(spacing=10); self.cap.set_halign(Gtk.Align.CENTER)
        self.outer.pack_start(self.cap,False,False,0)
        self.dot=button(icon='view-grid-symbolic',callback=lambda:self.expand(not self.expanded)); self.dot.set_tooltip_text('فتح الجزيرة / إغلاقها')
        self.cap.pack_start(self.dot,False,False,2)
        self.summary=button('…',callback=lambda:self.expand(not self.expanded))
        self.cap.pack_start(self.summary,False,False,0)
        self.cap.pack_start(button(icon='emblem-system-symbolic',callback=self.settings),False,False,2)
        self.reveal=Gtk.Revealer(); self.outer.pack_start(self.reveal,True,True,0)
        self.panel=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        self.panel.set_name('expanded-panel')
        self.panel.set_border_width(16); self.reveal.add(self.panel)
        info=Gtk.Box(spacing=12)
        self.panel.pack_start(info,False,False,0)
        clock_card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7)
        clock_card.set_valign(Gtk.Align.CENTER); clock_card.set_hexpand(True)
        self.clock_label=label(''); self.clock_label.get_style_context().add_class('clock')
        self.date_label=label(''); self.date_label.set_line_wrap(True)
        clock_card.pack_start(self.clock_label,False,False,0); clock_card.pack_start(self.date_label,False,False,0)
        credit=Gtk.LinkButton.new_with_label('https://open-meteo.com/','الطقس: Open-Meteo')
        credit.set_halign(Gtk.Align.START); credit.set_can_focus(False)
        clock_card.pack_start(credit,False,False,0)
        info.pack_start(clock_card,True,True,0)
        self.weather_card=Gtk.Frame(); self.weather_card.set_size_request(168,168)
        self.weather_card.get_style_context().add_class('weather-card')
        weather_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,margin=9)
        self.weather_card.add(weather_box); info.pack_end(self.weather_card,False,False,0)
        self.weather_city=label('الطقس'); self.weather_city.set_max_width_chars(21)
        weather_box.pack_start(self.weather_city,False,False,0)
        now=Gtk.Box(spacing=7); self.weather_icon=Gtk.Image.new_from_icon_name('weather-few-clouds-symbolic',Gtk.IconSize.DIALOG)
        self.weather_icon.set_pixel_size(max(12,round(30*getattr(self,'layout_scale',1)))); now.pack_start(self.weather_icon,False,False,0)
        self.weather_temp=label('— °C'); self.weather_temp.get_style_context().add_class('temperature'); now.pack_start(self.weather_temp,False,False,0)
        weather_box.pack_start(now,False,False,0)
        self.weather_description=label('حدّد موقعك لعرض الطقس'); self.weather_description.set_max_width_chars(23)
        weather_box.pack_start(self.weather_description,False,False,0)
        self.weather_range=label('العليا —°  /  الصغرى —°'); weather_box.pack_start(self.weather_range,False,False,0)
        self.location_button=button('تحديد الموقع',callback=self.choose_location)
        weather_box.pack_start(self.location_button,False,False,0)
        self.weather.connect('changed',self.update_weather)
        self.panel.pack_start(Gtk.Separator(),False,False,0)
        self.panel.pack_start(label('النوافذ المفتوحة'),False,False,0)
        scroll=Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(66); scroll.set_max_content_height(100); scroll.set_propagate_natural_height(True)
        self.apps=Gtk.FlowBox(); self.apps.set_selection_mode(Gtk.SelectionMode.NONE)
        self.apps.set_max_children_per_line(9); self.apps.set_min_children_per_line(1)
        self.app_scroll=scroll
        scroll.add(self.apps); self.panel.pack_start(scroll,True,True,0)
        self.panel.pack_start(Gtk.Separator(),False,False,0)
        self.controls=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); self.panel.pack_start(self.controls,False,False,0)
        self.keyboard_button=button(callback=self.keyboard.next); self.controls.pack_start(self.keyboard_button,False,False,0)
        self.audio_box=Gtk.Box(spacing=8); self.controls.pack_start(self.audio_box,False,False,0)
        self.mute=button(icon='audio-volume-high-symbolic',callback=self.audio.toggle); self.audio_box.pack_start(self.mute,False,False,0)
        self.scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1); self.scale.set_hexpand(True); self.scale.set_size_request(150,-1)
        self.scale.connect('value-changed',self.volume_changed)
        self.scale.connect('button-press-event',lambda *_:self.hold())
        self.scale.connect('button-release-event',lambda *_:self.release())
        self.audio_box.pack_start(self.scale,True,True,0)
        self.outputs=button(icon='audio-speakers-symbolic',callback=self.output_menu); self.outputs.set_tooltip_text('جهاز إخراج الصوت')
        self.audio_box.pack_start(self.outputs,False,False,0)
        row=Gtk.Box(spacing=8); self.controls.pack_start(row,False,False,0)
        self.netbutton=button(callback=self.network_menu); self.netbutton.set_hexpand(True); row.pack_start(self.netbutton,True,True,0)
        self.btbutton=button(callback=self.bluetooth_menu); row.pack_start(self.btbutton,False,False,0)
        self.batlabel=label(''); self.controls.pack_start(self.batlabel,False,False,0)
        self.status=label(self.config.warning); self.status.set_line_wrap(True); self.panel.pack_start(self.status,False,False,0)
        foot=Gtk.Box(spacing=8); self.panel.pack_start(foot,False,False,0)
        foot.pack_end(button('خروج',callback=self.quit),False,False,0)
        foot.pack_end(button('الإعدادات',callback=self.settings),False,False,0)
        self.registration_label=label('Register Bahaalden Hashim')
        self.registration_label.set_halign(Gtk.Align.CENTER)
        self.registration_label.set_tooltip_text('مسجّل باسم بهاء الدين هاشم')
        self.registration_label.get_style_context().add_class('registration')
        self.panel.pack_end(self.registration_label,False,False,0)
        for s in [self.keyboard,self.audio,self.network,self.bluez,self.battery]: s.connect('changed',self.update)
        self.windows.connect('changed',self.window_changed)
        Gdk.Screen.get_default().connect('monitors-changed',self.screen_changed)
        Gdk.Screen.get_default().connect('size-changed',self.screen_changed)
        self.layout_scale=1.0; self.layout_bases=[]
        def remember(widget):
            if isinstance(widget,Gtk.Box): self.layout_bases.append((widget,widget.get_spacing(),widget.get_border_width(),widget.get_margin_top(),widget.get_margin_bottom(),widget.get_margin_start(),widget.get_margin_end()))
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children(): remember(child)
        remember(self.panel)
        self.css=Gtk.CssProvider(); Gtk.StyleContext.add_provider_for_screen(w.get_screen(),self.css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.apply_style(); w.show_all(); self.update(); self.update_weather(); self.update_clock(); self.window_changed(); self.position()
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,self.stop)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGINT,self.stop)

    def stop(self): self.quit(); return False

    def draw_background(self,w,cr):
        cr.set_operator(cairo.OPERATOR_SOURCE); cr.set_source_rgba(0,0,0,0); cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        Gtk.render_background(w.get_style_context(),cr,0,0,w.get_allocated_width(),w.get_allocated_height())
        Gtk.render_frame(w.get_style_context(),cr,0,0,w.get_allocated_width(),w.get_allocated_height())
        return False

    def apply_style(self):
        s=getattr(self,'layout_scale',1.0)
        c=self.config['color']; r,g,b=[int(c[i:i+2],16) for i in (1,3,5)]
        self.css.load_from_data(f'''
        #island {{ background-color: rgba({r},{g},{b},{self.config['opacity']}); color: #edf2ff; border-radius: 20px; border: 1px solid #394052; }}
        #island button {{ color: #edf2ff; border-radius: 12px; padding: 7px; background: transparent; border: none; box-shadow: none; }}
        #island button:hover {{ background: #333e54; }}
        #island .clock {{ font-size: 31px; font-weight: bold; }}
        #island .temperature {{ font-size: 22px; font-weight: bold; }}
        #island .weather-card {{ border-radius: 16px; background: rgba(120,150,200,0.09); border: 1px solid #414e64; }}
        #island .weather-card > border {{ border: none; }}
        #island .bluetooth-on {{ background: #244b75; color: #b9ddff; }}
        #island .bluetooth-off {{ background: #30333b; color: #c3c7d0; }}
        #island .active {{ background: #334d76; border-bottom: 2px solid #8cbcff; }}
        #island label {{ color: #edf2ff; }}
        #island scale highlight {{ background: #8cbcff; }}
        #island separator {{ background: #394052; }}
        #island #expanded-panel {{ font-size: {max(7,13*s):.2f}px; }}
        #island #expanded-panel button {{ padding: {max(1,7*s):.2f}px; min-height: 0; min-width: 0; border-radius: {12*s:.2f}px; }}
        #island #expanded-panel .registration {{ color: #a7b3c9; font-size: {max(7,10*s):.2f}px; }}
        #island #expanded-panel .clock {{ font-size: {31*s:.2f}px; }}
        #island #expanded-panel .temperature {{ font-size: {22*s:.2f}px; }}
        #island #expanded-panel scale {{ padding: {5*s:.2f}px; min-height: 0; }}
        #island #expanded-panel scale trough {{ min-height: {max(2,4*s):.2f}px; }}
        #island #expanded-panel scale slider {{ min-width: {max(7,16*s):.2f}px; min-height: {max(7,16*s):.2f}px; margin: 0; }}
        #island #expanded-panel flowbox {{ padding: 0; }}
        #island #expanded-panel flowboxchild {{ padding: {2*s:.2f}px; min-height: 0; min-width: 0; }}
        #island #expanded-panel .weather-card {{ border-radius: {16*s:.2f}px; }}
        '''.encode())
        self.reveal.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN if self.config['animations'] else Gtk.RevealerTransitionType.NONE)
        self.reveal.set_transition_duration(140)

    def screen_changed(self,*_):
        if self.expanded: self.layout_panel()
        self.position()

    def position(self):
        if not self.window: return
        display=Gdk.Display.get_default(); n=display.get_n_monitors()
        if not n: return
        m=display.get_monitor(min(self.config['monitor'],n-1)); rect=m.get_geometry()
        width,height=self.window.get_size()
        x=max(rect.x,min(rect.x+rect.width-width,rect.x+(rect.width-width)//2+self.config['offset']))
        target=(x,rect.y+min(self.config['top'],max(0,rect.height-height)))
        if getattr(self,'last_position',None)!=target:
            self.window.move(*target); self.last_position=target

    def allocated(self,w,allocation):
        # Shape both the visible and input regions, so invisible corners pass clicks through.
        width,height=allocation.width,allocation.height
        if getattr(self,'last_shape',None)==(width,height):
            self.position(); return
        self.last_shape=(width,height)
        region=cairo.Region(); radius=min(20,height//2)
        if height>2*radius: region.union(cairo.RectangleInt(0,radius,width,height-2*radius))
        for y in list(range(radius))+list(range(height-radius,height)):
            dy=max(0,radius-y-0.5,y+0.5-(height-radius))
            inset=math.ceil(radius-math.sqrt(max(0,radius*radius-dy*dy))) if dy else 0
            region.union(cairo.RectangleInt(inset,y,max(1,width-2*inset),1))
        if w.get_window():
            w.get_window().input_shape_combine_region(region,0,0)
            w.get_window().shape_combine_region(region,0,0)
        self.position()

    def enter(self,*_):
        if self.close_timer: GLib.source_remove(self.close_timer); self.close_timer=0
        if not self.expanded and not self.open_timer and GLib.get_monotonic_time()>=getattr(self,'hover_until',0):
            self.open_timer=GLib.timeout_add(self.config['open_delay'],self.hover_open)
        return False

    def hover_open(self): self.open_timer=0; self.expand(True); return False

    def leave(self,w,event):
        if event.detail==Gdk.NotifyType.INFERIOR: return False
        if self.open_timer: GLib.source_remove(self.open_timer); self.open_timer=0
        self.schedule_close(); return False

    def schedule_close(self):
        if self.close_timer: GLib.source_remove(self.close_timer)
        self.close_timer=GLib.timeout_add(self.config['close_delay'],self.maybe_close)

    def maybe_close(self):
        self.close_timer=0
        if self.busy or any(p.get_visible() for p in self.popovers) or self.settings_window or self.location_dialog: return False
        pointer=Gdk.Display.get_default().get_default_seat().get_pointer()
        _,x,y=pointer.get_position(); wx,wy=self.window.get_position(); width,height=self.window.get_size()
        if not (wx<=x<wx+width and wy<=y<wy+height): self.expand(False)
        return False

    def hold(self): self.busy+=1; return False
    def release(self): self.busy=max(0,self.busy-1); self.schedule_close(); return False

    def expand(self,expanded):
        if not expanded and self.busy: return
        self.expanded=expanded
        if not expanded:
            self.hover_until=GLib.get_monotonic_time()+400000
            if self.open_timer: GLib.source_remove(self.open_timer); self.open_timer=0
        if expanded:
            self.panel.show()
            self.layout_panel()
            self.update_clock(); self.weather.refresh()
            if not self.weather_timer: self.weather_timer=GLib.timeout_add_seconds(900,self.weather_tick)
        else:
            for name in ('clock_timer','weather_timer'):
                timer=getattr(self,name,0)
                if timer: GLib.source_remove(timer); setattr(self,name,0)
        self.reveal.set_reveal_child(expanded)
        if not expanded: self.panel.set_size_request(-1,-1)
        # GtkWindow does not shrink automatically after the revealer animation.
        GLib.timeout_add(170,self.shrink)

    def panel_size(self):
        display=Gdk.Display.get_default()
        rect=display.get_monitor(min(self.config['monitor'],display.get_n_monitors()-1)).get_geometry()
        return min(self.config['width'],rect.width-20), min(self.config['height'],rect.height-12)

    def layout_panel(self):
        width,height=self.panel_size()
        self.layout_scale=panel_metrics(width,height)
        self.apply_panel_metrics()
        # Reserve the capsule's natural height, independent of expanded sizing.
        cap_height=self.cap.get_preferred_height()[1]
        self.panel.set_size_request(max(1,width),max(1,height-cap_height))
        self.fit_attempts=0
        GLib.idle_add(self.fit_panel)

    def apply_panel_metrics(self):
        s=self.layout_scale
        for widget,spacing,border,top,bottom,start,end in self.layout_bases:
            widget.set_spacing(round(spacing*s)); widget.set_border_width(round(border*s))
            widget.set_margin_top(round(top*s)); widget.set_margin_bottom(round(bottom*s))
            widget.set_margin_start(round(start*s)); widget.set_margin_end(round(end*s))
        side=round(168*s); self.weather_card.set_size_request(side,side)
        self.weather_icon.set_pixel_size(max(12,round(30*s)))
        self.scale.set_size_request(round(150*s),-1)
        self.app_scroll.set_max_content_height(-1)
        self.app_scroll.set_min_content_height(round(66*s)); self.app_scroll.set_max_content_height(round(100*s))
        self.apps.set_column_spacing(round(6*s)); self.apps.set_row_spacing(round(6*s))
        def images(widget):
            if isinstance(widget,Gtk.Image) and widget is not self.weather_icon:
                pix=widget.get_pixbuf() if widget.get_storage_type()==Gtk.ImageType.PIXBUF else None
                if pix:
                    if not hasattr(widget,'original_icon'): widget.original_icon=pix
                    side=max(12,round(30*s)); widget.set_from_pixbuf(widget.original_icon.scale_simple(side,side,2))
                else: widget.set_pixel_size(max(10,round(16*s)))
            if isinstance(widget,Gtk.Button):
                child=widget.get_child()
                if isinstance(child,Gtk.Label): child.set_ellipsize(Pango.EllipsizeMode.END)
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children(): images(child)
        images(self.panel)
        self.apply_style()

    def fit_panel(self):
        if not self.expanded: return False
        width,height=self.panel_size()
        # Measure natural content without the user's size request masking it.
        self.panel.set_size_request(-1,-1)
        minimum=self.panel.get_preferred_height_for_width(max(1,width))[1]
        needed_width=self.panel.get_preferred_width()[0]
        available=height-self.cap.get_preferred_height()[1]
        if (minimum>available or needed_width>width) and self.fit_attempts<10:
            ratio=min(available/max(1,minimum),width/max(1,needed_width))
            self.layout_scale=max(.28,self.layout_scale*min(.94,ratio*.96))
            self.apply_panel_metrics(); self.fit_attempts+=1
            GLib.idle_add(self.fit_panel)
        self.panel.set_size_request(max(1,width),max(1,available))
        self.window.resize(width,height)
        return False

    def shrink(self):
        if not self.expanded and not self.reveal.get_child_revealed(): self.panel.hide()
        self.window.resize(1,1); self.position(); return False

    def key(self,w,e):
        if e.keyval==Gdk.KEY_Escape: self.expand(False); return True
        return False

    def window_changed(self,*_):
        for child in self.apps.get_children(): self.apps.remove(child)
        for win in self.windows.items(self.config['all_workspaces']):
            b=button(callback=lambda w=win:self.choose_window(w))
            pix=win.get_icon()
            b.set_image(Gtk.Image.new_from_pixbuf(pix.scale_simple(30,30,2)) if pix else Gtk.Image.new_from_icon_name('application-x-executable',Gtk.IconSize.LARGE_TOOLBAR))
            space=win.get_workspace()
            b.set_tooltip_text(win.get_name()+(f' · {space.get_name()}' if space else ''))
            if win.is_active(): b.get_style_context().add_class('active')
            self.apps.add(b)
        self.apps.show_all()
        if self.expanded: self.layout_panel()
        if self.config['hide_fullscreen'] and self.windows.fullscreen() and not self.busy and not self.settings_window and not self.location_dialog: self.window.hide()
        else: self.window.show()

    def choose_window(self,win):
        self.windows.activate(win,Gtk.get_current_event_time()); self.expand(False)

    def update(self,*_):
        c=self.config; k=self.keyboard; a=self.audio; n=self.network; bt=self.bluez
        summary=[]
        if c['show_keyboard']: summary.append(k.label)
        if c['show_network']: summary.append('●' if n.client and n.client.get_state()==70 else '○')
        if c['show_audio']: summary.append(('🔇' if a.muted else '♪')+f' {a.volume}%')
        if c['show_battery'] and self.battery.present: summary.append(self.battery.label.split(' · ')[0])
        self.summary.set_label('   ·   '.join(summary) or 'الجزيرة')
        self.keyboard_button.set_label('لغة لوحة المفاتيح: '+k.label+'   ↔')
        self.keyboard_button.set_sensitive(bool(k.layouts)); self.keyboard_button.set_visible(c['show_keyboard'])
        self.audio_box.set_visible(c['show_audio']); self.audio_box.set_sensitive(a.available)
        self.audio_box.set_tooltip_text(a.error if not a.available else None)
        self.audio_sync=True; self.scale.set_value(min(100,a.volume)); self.audio_sync=False
        self.mute.set_image(Gtk.Image.new_from_icon_name('audio-volume-muted-symbolic' if a.muted else 'audio-volume-high-symbolic',Gtk.IconSize.BUTTON))
        self.netbutton.set_tooltip_text(n.label)
        self.netbutton.set_label(n.label); self.netbutton.set_visible(c['show_network']); self.netbutton.set_sensitive(bool(n.client))
        powered=bool(bt.adapters and bt.prop(bt.adapters[0],'Powered',False))
        self.btbutton.set_label(('Bluetooth · مفعّل' if powered else 'Bluetooth · متوقف') if bt.adapters else 'Bluetooth غير متاح')
        style=self.btbutton.get_style_context()
        for cls in ('bluetooth-on','bluetooth-off'): style.remove_class(cls)
        style.add_class('bluetooth-on' if powered else 'bluetooth-off')
        self.btbutton.set_tooltip_text('الأزرق: مفعّل · الرمادي: متوقف' if bt.adapters else 'لا يوجد محول Bluetooth')
        self.btbutton.set_visible(c['show_bluetooth']); self.btbutton.set_sensitive(bool(bt.adapters))
        self.batlabel.set_text('البطارية: '+self.battery.label)
        self.batlabel.set_visible(c['show_battery'] and self.battery.present)
        self.shrink()

    def update_clock(self):
        now=datetime.now().astimezone()
        weekdays=('الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد')
        months=('يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر')
        self.clock_label.set_text(now.strftime('%H:%M'))
        self.date_label.set_text(f'{weekdays[now.weekday()]}\n{now.day} {months[now.month-1]} {now.year}')
        if self.clock_timer: GLib.source_remove(self.clock_timer); self.clock_timer=0
        if self.expanded:
            self.clock_timer=GLib.timeout_add(max(100,round((60-now.second-now.microsecond/1000000)*1000)),self.clock_tick)

    def clock_tick(self):
        self.clock_timer=0; self.update_clock(); return False

    def weather_tick(self):
        if self.expanded: self.weather.refresh(); return True
        self.weather_timer=0; return False

    def update_weather(self,*_):
        weather=self.weather; place=weather.place; data=weather.data
        self.weather_city.set_text(place['city'] if place else 'الطقس')
        self.weather_city.set_tooltip_text(place['city'] if place else None)
        self.location_button.set_label('تغيير الموقع' if place else 'تحديد الموقع')
        if data:
            self.weather_icon.set_from_icon_name(data['icon'],Gtk.IconSize.DIALOG); self.weather_icon.set_pixel_size(max(12,round(30*getattr(self,'layout_scale',1))))
            self.weather_temp.set_text(f"{data['temperature']:.0f} °C")
            self.weather_range.set_text(f"العليا {data['high']:.0f}°  /  الصغرى {data['low']:.0f}°")
            self.weather_description.set_text(data['description']+(' · قديم' if weather.error else ''))
        else:
            self.weather_icon.set_from_icon_name('weather-few-clouds-symbolic',Gtk.IconSize.DIALOG); self.weather_icon.set_pixel_size(max(12,round(30*getattr(self,'layout_scale',1))))
            self.weather_temp.set_text('— °C'); self.weather_range.set_text('العليا —°  /  الصغرى —°')
            self.weather_description.set_text('جارٍ تحميل الطقس…' if weather.loading else ('الطقس غير متاح' if weather.error else 'حدّد موقعك لعرض الطقس'))
        self.weather_card.set_tooltip_text(weather.error or ('Open-Meteo · '+data['time'] if data else 'الموقع يُحفظ محليًا خارج المشروع'))

    def choose_location(self):
        if self.location_dialog: self.location_dialog.present(); return
        self.expand(True)
        dialog=Gtk.Dialog(title='موقع الطقس',transient_for=self.window)
        self.location_dialog=dialog
        dialog.add_button('إغلاق',Gtk.ResponseType.CLOSE); dialog.set_default_size(430,300)
        box=dialog.get_content_area(); box.set_border_width(16); box.set_spacing(10)
        help_label=label('الموقع يُحفظ في إعدادات حسابك فقط، خارج المشروع.'); help_label.set_line_wrap(True)
        box.pack_start(help_label,False,False,0)
        automatic=button('تحديد موقعي تلقائيًا (تقريبي)',callback=lambda:resolve(True))
        box.pack_start(automatic,False,False,0)
        row=Gtk.Box(spacing=7); entry=Gtk.Entry(); entry.set_placeholder_text('أو أدخل اسم المدينة بنفسك')
        row.pack_start(entry,True,True,0); search=button('بحث',callback=lambda:resolve(False)); row.pack_start(search,False,False,0)
        box.pack_start(row,False,False,0)
        message=label(''); message.set_line_wrap(True); box.pack_start(message,False,False,0)
        results=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4); box.pack_start(results,True,True,0)
        def selected(place):
            try: self.weather.set_location(place)
            except OSError: message.set_text('تعذر حفظ الموقع في إعدادات الحساب.'); return
            dialog.response(Gtk.ResponseType.CLOSE)
        def complete(places,error):
            if self.location_dialog is not dialog: return
            automatic.set_sensitive(True); search.set_sensitive(True)
            message.set_text(error or 'اختر الموقع لتأكيده وعرض طقسه:')
            for child in results.get_children(): results.remove(child)
            for place in places: results.pack_start(button(place['city'],callback=lambda p=place:selected(p)),False,False,0)
            results.show_all()
        def resolve(auto):
            if not auto and not entry.get_text().strip(): message.set_text('اكتب اسم المدينة أولًا.'); return
            if auto:
                consent=Gtk.MessageDialog(transient_for=dialog,modal=True,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.OK_CANCEL,text='السماح بتحديد موقعك التقريبي؟')
                consent.format_secondary_text('سيتصل التطبيق بخدمة ipwho.is التي سترى عنوان الإنترنت العام لتقدير المدينة. بعد تأكيد الموقع تُرسل إحداثياته إلى Open-Meteo لجلب الطقس. قد يكون الموقع غير دقيق مع VPN. لن يُحفظ عنوان الإنترنت أو الموقع داخل المشروع.')
                answer=consent.run(); consent.destroy()
                if answer!=Gtk.ResponseType.OK: return
            automatic.set_sensitive(False); search.set_sensitive(False); message.set_text('جارٍ البحث…')
            self.weather.resolve(entry.get_text().strip(),auto,complete)
        entry.connect('activate',lambda *_:resolve(False))
        clear=button('حذف الموقع المحفوظ',callback=lambda:forget())
        clear.set_sensitive(bool(self.weather.place)); box.pack_start(clear,False,False,0)
        def forget():
            try: self.weather.clear_location()
            except OSError: message.set_text('تعذر حذف الموقع من الإعدادات.'); return
            dialog.response(Gtk.ResponseType.CLOSE)
        def closed(*_): self.location_dialog=None; dialog.destroy(); self.schedule_close()
        dialog.connect('response',closed)
        dialog.connect('key-press-event',lambda w,e:(dialog.response(Gtk.ResponseType.CLOSE) or True) if e.keyval==Gdk.KEY_Escape else False)
        dialog.show_all(); dialog.present()

    def volume_changed(self,scale):
        if not self.audio_sync:
            if getattr(self,'volume_timer',0): GLib.source_remove(self.volume_timer)
            self.volume_timer=GLib.timeout_add(70,self.commit_volume)
    def commit_volume(self): self.volume_timer=0; self.audio.set_volume(self.scale.get_value()); return False

    def popover(self,anchor):
        pop=Gtk.Popover.new(anchor); pop.set_modal(False); pop.set_position(Gtk.PositionType.BOTTOM)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5); box.set_border_width(10)
        pop.add(box); self.popovers.append(pop)
        def closed(*_):
            if pop in self.popovers: self.popovers.remove(pop)
            pop.destroy(); self.schedule_close()
        pop.connect('closed',closed)
        pop.connect('key-press-event',lambda w,e:(pop.popdown() or True) if e.keyval==Gdk.KEY_Escape else False)
        return pop,box

    def output_menu(self):
        pop,box=self.popover(self.outputs)
        for sink in self.audio.sinks:
            box.pack_start(button(sink.get('description',sink['name']),callback=lambda n=sink['name']:(self.audio.output(n),pop.popdown())),False,False,0)
        pop.show_all()

    def network_menu(self):
        n=self.network; pop,box=self.popover(self.netbutton)
        box.pack_start(label(n.label),False,False,0)
        toggle=button('إيقاف Wi-Fi' if n.client and n.client.wireless_get_enabled() else 'تشغيل Wi-Fi',callback=lambda:(n.toggle(),pop.popdown()))
        toggle.set_sensitive(bool(n.wifi and n.client.wireless_hardware_get_enabled())); box.pack_start(toggle,False,False,0)
        if not n.wifi: box.pack_start(label('لا يوجد محول Wi-Fi'),False,False,0)
        scroll=Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); scroll.set_max_content_height(230); scroll.set_propagate_natural_height(True)
        networks=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3); scroll.add(networks); box.pack_start(scroll,True,True,0)
        for ap in n.access_points():
            ssid=n.ssid(ap)
            b=button(f'{ssid}   {ap.get_strength()}%',callback=lambda ap=ap:(pop.popdown(),self.connect_network(ap)))
            b.set_sensitive(n.client.wireless_get_enabled()); networks.pack_start(b,False,False,0)
        box.pack_start(button('تحديث قائمة الشبكات',callback=lambda:(n.scan(),pop.popdown())),False,False,0)
        box.pack_start(button('إعدادات الشبكة والمصادقة',callback=lambda:self.external(['nm-connection-editor'])),False,False,0)
        pop.show_all()

    def connect_network(self,ap):
        # Terminal asks for secrets itself; passwords never enter this process or logs.
        argv=['xfce4-terminal','--disable-server','--title=اتصال Wi-Fi','--execute','nmcli','--ask','device','wifi','connect',ap.get_bssid(),'ifname',self.network.wifi.get_iface()]
        self.external(argv)

    def bluetooth_menu(self):
        bt=self.bluez; pop,box=self.popover(self.btbutton)
        powered=bt.adapters and bt.prop(bt.adapters[0],'Powered',False)
        box.pack_start(button('إيقاف Bluetooth' if powered else 'تشغيل Bluetooth',callback=lambda:(bt.toggle(),pop.popdown())),False,False,0)
        devices=[d for d in bt.interfaces('org.bluez.Device1') if bt.prop(d,'Paired',False) or bt.prop(d,'Connected',False)]
        if not devices: box.pack_start(label('لا توجد أجهزة مقترنة'),False,False,0)
        for d in devices:
            connected=bt.prop(d,'Connected',False)
            b=button(f"{bt.prop(d,'Alias','جهاز')} · {'فصل' if connected else 'اتصال'}",callback=lambda d=d,c=connected:(bt.call(d,'Disconnect' if c else 'Connect'),pop.popdown()))
            b.set_sensitive(bool(powered)); box.pack_start(b,False,False,0)
        box.pack_start(button('الإقران وإعدادات Bluetooth',callback=lambda:self.external(['blueman-manager'])),False,False,0)
        if bt.error: box.pack_start(label(bt.error),False,False,0)
        pop.show_all()

    def external(self,argv):
        try: p=subprocess.Popen(argv)
        except OSError as e: self.status.set_text(str(e)); return
        self.hold()
        def wait():
            p.wait(); GLib.idle_add(self.release)
        import threading
        threading.Thread(target=wait,daemon=True).start()

    def settings(self):
        if self.settings_window: self.settings_window.present(); return
        self.expand(True)
        dialog=Gtk.Dialog(title='إعدادات الجزيرة',transient_for=self.window,destroy_with_parent=True)
        dialog.set_default_size(470,570); dialog.add_button('إلغاء',Gtk.ResponseType.CANCEL); dialog.add_button('حفظ',Gtk.ResponseType.OK)
        self.settings_window=dialog
        original_size=(self.config['width'],self.config['height'])
        scroll=Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        dialog.get_content_area().pack_start(scroll,True,True,0)
        grid=Gtk.Grid(column_spacing=16,row_spacing=9,margin=18); scroll.add(grid); fields={}
        names={'monitor':'رقم الشاشة (بدءًا من 0)','top':'المسافة من الأعلى','offset':'الإزاحة الأفقية','width':'عرض اللوحة المفتوحة (بكسل)','height':'ارتفاع اللوحة المفتوحة (بكسل)','opacity':'الشفافية','color':'لون الخلفية','open_delay':'مهلة الفتح (مللي ثانية)','close_delay':'مهلة الإغلاق (مللي ثانية)','animations':'الحركة','hide_fullscreen':'إخفاء أثناء ملء الشاشة','all_workspaces':'نوافذ جميع مساحات العمل','show_keyboard':'إظهار اللغة','show_audio':'إظهار الصوت','show_network':'إظهار الشبكة','show_bluetooth':'إظهار Bluetooth','show_battery':'إظهار البطارية'}
        limits={'monitor':(0,max(0,Gdk.Display.get_default().get_n_monitors()-1),1),'top':(0,400,1),'offset':(-4000,4000,1),'width':(320,1600,10),'height':(340,1400,10),'opacity':(0.3,1,0.01),'open_delay':(0,3000,10),'close_delay':(100,5000,10)}
        hint=label('العرض والارتفاع يخصّان اللوحة المفتوحة فقط، وتُصغّر المحتويات معهما. تُقيَّد الأبعاد بمساحة الشاشة. المعاينة مباشرة؛ إلغاء يعيد المقاس السابق.')
        hint.set_line_wrap(True); hint.set_max_width_chars(45)
        grid.attach(hint,0,len(names),2,1)
        self.settings_fields=fields
        for row,(key,text) in enumerate(names.items()):
            value=self.config[key]; grid.attach(label(text),0,row,1,1)
            if type(value) is bool:
                widget=Gtk.Switch(); widget.set_active(value); widget.set_halign(Gtk.Align.END)
            elif key=='color':
                widget=Gtk.ColorButton(); rgba=Gdk.RGBA(); rgba.parse(value); widget.set_rgba(rgba)
            else:
                widget=Gtk.SpinButton.new_with_range(*limits[key]); widget.set_value(value)
                if key=='opacity': widget.set_digits(2)
            fields[key]=widget; grid.attach(widget,1,row,1,1)
        def preview_size(*_):
            self.config.data['width']=fields['width'].get_value_as_int()
            self.config.data['height']=fields['height'].get_value_as_int()
            self.layout_panel()
        for key in ('width','height'): fields[key].connect('value-changed',preview_size)
        dialog.connect('key-press-event',lambda w,e:(dialog.response(Gtk.ResponseType.CANCEL) or True) if e.keyval==Gdk.KEY_Escape else False)
        def response(d,result):
            if result==Gtk.ResponseType.OK:
                for key,widget in fields.items():
                    if isinstance(widget,Gtk.Switch): value=widget.get_active()
                    elif isinstance(widget,Gtk.ColorButton):
                        c=widget.get_rgba(); value='#{:02x}{:02x}{:02x}'.format(round(c.red*255),round(c.green*255),round(c.blue*255))
                    else: value=widget.get_value() if key=='opacity' else widget.get_value_as_int()
                    self.config.data[key]=value
                try: self.config.save(); self.status.set_text('تم حفظ الإعدادات')
                except OSError: self.status.set_text('تعذر حفظ الإعدادات')
                self.apply_style(); self.update(); self.window_changed(); self.expand(self.expanded)
            if result!=Gtk.ResponseType.OK:
                self.config.data['width'],self.config.data['height']=original_size
                self.layout_panel()
            self.settings_window=None; d.destroy(); self.schedule_close()
        dialog.connect('response',response); dialog.show_all(); dialog.present()

    def shutdown_app(self,*_):
        for name in ('clock_timer','weather_timer'):
            timer=getattr(self,name,0)
            if timer: GLib.source_remove(timer); setattr(self,name,0)
        if hasattr(self,'audio'): self.audio.close()
        if hasattr(self,'windows'):
            for child in self.apps.get_children(): self.apps.remove(child)
            self.windows.close()
        if self.window: self.window.destroy()
        import gc
        gc.collect()
        # Keep libwnck global screen alive until process exit: Python wrappers may
        # still reference windows during GI finalization.


def main():
    if os.environ.get('XDG_SESSION_TYPE')=='wayland':
        print('Floating Island requires an X11 session.',file=sys.stderr); return 1
    return Island().run(sys.argv)

if __name__=='__main__': sys.exit(main())
