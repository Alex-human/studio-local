"""Cost of long editing operations (GUIA_EDICION.md → «Flujo de trabajo adaptable»). A nested operation counts inside the outer one."""
import contextlib, contextvars, json, re, resource, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/'costes.jsonl'
# Energy of the whole Mac from the battery/charger telemetry (on battery too): it sums the system load in mW once per
# second and publishes every ~45 s.
ENERGY=['/usr/sbin/ioreg','-r','-n','AppleSmartBattery','-w0']
current=contextvars.ContextVar('cost',default=None)

def cpu():
    return sum(r.ru_utime+r.ru_stime for r in map(resource.getrusage,(resource.RUSAGE_SELF,resource.RUSAGE_CHILDREN)))

def energy_reader():
    try:return subprocess.Popen(ENERGY,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    except OSError:return None

def energy_read(reader):
    """(mW summed, samples, last mW) as last published."""
    try:out=reader.communicate(timeout=2)[0];return tuple(int(re.search(f'"{k}"=(\\d+)',out)[1]) for k in ('AccumulatedSystemLoad','SystemLoadAccumulatorCount','SystemLoad'))
    except (AttributeError,TypeError,subprocess.TimeoutExpired):return None

def joules(first,last,seconds):
    """Mean power between the two publications (the last one if none came between) × the real duration."""
    (a0,n0,_),(a1,n1,w1)=first,last
    return round((a1-a0)/(n1-n0)*seconds/1000 if n1>n0 else w1*seconds/1000)

@contextlib.contextmanager
def measured(operation, project=None):
    if current.get() is not None:
        yield current.get();return
    entry=dict(operation=operation);token=current.set(entry)
    start,used,before=time.monotonic(),cpu(),energy_reader()
    try: yield entry
    finally:
        current.reset(token);seconds=time.monotonic()-start
        if seconds>=5:
            path=project and Path(project)
            first,last=energy_read(before),energy_read(energy_reader())
            entry=dict(date=time.strftime('%Y-%m-%d %H:%M'),**entry,project=path and (path.parent.name if path.suffix=='.studio' else path.name),
                       seconds=round(seconds,1),cpu=round(cpu()-used,1),**({'joules':joules(first,last,seconds)} if first and last else {}))
            try:
                with LOG.open('a') as log: log.write(json.dumps(entry,ensure_ascii=False)+'\n')
            except OSError: pass   # the log never makes an edit fail
        elif before:before.kill();before.communicate()

if __name__=='__main__':
    since=sys.argv[1] if len(sys.argv)>1 else ''; totals={}
    for entry in map(json.loads,LOG.read_text().splitlines() if LOG.exists() else []):
        if entry['date']>=since:
            name=' · '.join(filter(None,(entry['operation'],entry.get('detail'))))
            total=totals.setdefault(name,[0,0,0,0]); total[0]+=1; total[1]+=entry['seconds']; total[2]+=entry['cpu']; total[3]+=entry.get('joules',0)
    for name,(n,seconds,used,energy) in sorted(totals.items(),key=lambda item:(-item[1][3],-item[1][2])):
        print(f'{name}: {n} veces · {seconds/60:.1f} min · {used:.0f} núcleo·s · {energy/1000:.1f} kJ')
