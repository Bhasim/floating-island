#!/usr/bin/python3
"""Measures app process only; does not change hardware/system settings."""
import ctypes as C
import ctypes.util
import json
import os
from pathlib import Path
import subprocess
import time

root=Path(__file__).resolve().parents[1]
launcher=root/'run.sh'
hz=os.sysconf('SC_CLK_TCK')
log=open('/tmp/floating-island-benchmark.log','w')
x=C.CDLL(ctypes.util.find_library('X11')); xt=C.CDLL(ctypes.util.find_library('Xtst'))
x.XOpenDisplay.argtypes=[C.c_char_p]; x.XOpenDisplay.restype=C.c_void_p
xd=x.XOpenDisplay(None)
x.XDefaultRootWindow.argtypes=[C.c_void_p]; x.XDefaultRootWindow.restype=C.c_ulong
rootwin=x.XDefaultRootWindow(xd)
x.XQueryPointer.argtypes=[C.c_void_p,C.c_ulong]+[C.c_void_p]*7
rr=C.c_ulong(); child=C.c_ulong(); rx=C.c_int(); ry=C.c_int(); wx=C.c_int(); wy=C.c_int(); mask=C.c_uint()
x.XQueryPointer(xd,rootwin,C.byref(rr),C.byref(child),C.byref(rx),C.byref(ry),C.byref(wx),C.byref(wy),C.byref(mask))
xt.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]; x.XFlush.argtypes=[C.c_void_p]
def move(px,py): xt.XTestFakeMotionEvent(xd,-1,px,py,0); x.XFlush(xd)
move(10,500)
process=subprocess.Popen([str(launcher)],stdout=log,stderr=log)
time.sleep(2)
if process.poll() is not None:
    move(rx.value,ry.value); log.close()
    raise SystemExit('Application did not start; stop existing instance before benchmarking.')
pid=process.pid

def sample():
    fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    ticks=int(fields[11])+int(fields[12])
    status=Path(f'/proc/{pid}/status').read_text().splitlines()
    rss=int(next(s.split()[1] for s in status if s.startswith('VmRSS:')))
    return ticks,rss

def command(arg): subprocess.run([str(launcher),arg],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)

def measure(name,duration,interact=False):
    geometry=next((line.split()[4:6] for line in subprocess.check_output(['wmctrl','-lG'],text=True).splitlines() if line.endswith(' Floating Island')),[])
    t0=time.monotonic(); ticks,_=sample(); rss=[]; cycles=0
    while time.monotonic()-t0<duration:
        if interact:
            command('--expand'); time.sleep(.2); command('--collapse'); cycles+=1
        else: time.sleep(.5)
        rss.append(sample()[1])
    dt=time.monotonic()-t0; last,_=sample()
    return {'mode':name,'initial_size':geometry,'seconds':round(dt,2),'cpu_percent_one_core':round((last-ticks)/hz/dt*100,3),'rss_min_mib':round(min(rss)/1024,2),'rss_max_mib':round(max(rss)/1024,2),'cycles':cycles}

try:
    command('--collapse'); time.sleep(.5)
    results=[measure('collapsed idle',20)]
    command('--expand'); time.sleep(.3)
    results.append(measure('expanded idle',15))
    results.append(measure('expand and collapse',15,True))
    command('--quit'); process.wait(timeout=8)
    report={'process_only':True,'exit_code':process.returncode,'results':results}
    (root/'docs/performance.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
finally:
    if process.poll() is None: process.terminate(); process.wait(timeout=8)
    log.close()
    move(rx.value,ry.value)
