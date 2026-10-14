"""Stage signed builds; replace the bundle only after its host has exited."""
import argparse,json,os,shutil,subprocess,time
from pathlib import Path
import fcntl
ROOT=Path(__file__).resolve().parents[1]
PENDING=ROOT/'.build/pending-update.json'

def atomic(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value));os.replace(temp,path)
def verified_stage(value):
    stage=Path(value).resolve()
    if stage.parent!=ROOT/'.build' or not stage.name.startswith('app-'):raise ValueError('Build fuera de la carpeta de preparación')
    bundle=stage/'Studio Local.app'
    subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(bundle)],check=True)
    if not (stage/'probe').is_file():raise ValueError('Falta probe en el build')
    return stage

def running():
    if not (ROOT/'Studio Local.app').exists():return False
    code=subprocess.run(['/usr/bin/pgrep','-x','StudioLocal'],stdout=subprocess.DEVNULL).returncode
    if code not in (0,1):raise RuntimeError('No se pudo comprobar si Studio Local está abierto')
    return code==0

def promote(stage):
    if running():raise RuntimeError('La aplicación sigue abierta; actualización conservada para después')
    target=ROOT/'Studio Local.app';backup=stage/'previous.app-backup';bundle=stage/'Studio Local.app'
    if target.exists():target.rename(backup)
    try:
        bundle.rename(target)
        os.replace(stage/'probe',ROOT/'runtime/probe')
    except BaseException:
        if target.exists() and not bundle.exists():target.rename(bundle)
        if backup.exists():backup.rename(target)
        raise
    if backup.exists():shutil.rmtree(backup)
    stage.rmdir()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage');parser.add_argument('--wait-pid',type=int);args=parser.parse_args()
    if args.wait_pid:
        deadline=time.monotonic()+30
        while True:
            try:os.kill(args.wait_pid,0)
            except ProcessLookupError:break
            if time.monotonic()>deadline:raise RuntimeError('El editor no se cerró; build sin instalar')
            time.sleep(.2)
    with (ROOT/'.build/update.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        stage=verified_stage(args.stage or json.loads(PENDING.read_text())['stage'])
        if running():
            if args.wait_pid:raise RuntimeError('Hay otra instancia abierta; no se sustituye el bundle')
            atomic(PENDING,{'stage':str(stage)});print('Build preparado. Studio lo instalará al pausar y guardar la sesión.');return
        promote(stage)
        if PENDING.exists():PENDING.unlink()
    if args.wait_pid:subprocess.run(['/usr/bin/open',str(ROOT/'Studio Local.app')],check=True)
    print('Studio Local actualizado.')
if __name__=='__main__':main()
