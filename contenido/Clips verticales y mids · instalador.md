# Tu máquina de contenido · instalador para Mac

Versión 2.1 · 14 de octubre de 2026

## Empieza aquí

Este archivo enseña a tu IA a convertir grabaciones largas en contenido para tu canal. Tú le explicas a quién hablas y qué aspecto quieres; ella prepara las herramientas, propone los mejores momentos y edita los vídeos contigo.

1. Descarga este archivo en tu Mac.
2. Abre **Claude Code en modo local** —la opción recomendada para este recorrido— o **Codex en local**, con acceso a la carpeta donde lo has descargado.
3. Pega esta frase, indicando el archivo descargado:

> Instala mi máquina de contenido siguiendo este archivo. Explícame lo necesario sin tecnicismos, pregúntame por mi canal y mi estilo, ofréceme Studio Local y ayúdame a hacer una primera prueba. No sé programar.

La IA te irá preguntando de pocas en pocas. No tienes que copiar código ni manejar la terminal. Si ya tienes una grabación, puedes dársela desde el principio.

El editor es [Studio Local](https://github.com/Alex-human/studio-local). Si descargas el ZIP completo, su código está incluido; si usas solo este archivo, la IA lo descarga de ese repositorio. Las dependencias y modelos se obtienen durante la instalación: se necesita internet.

## Qué vas a tener

- **Clips verticales:** Reels, Shorts y TikToks con una idea completa, cortes cuidados, encuadre, gancho y subtítulos con tus colores.
- **YouTube Mids** (a veces llamados «meets»): vídeos horizontales sacados de llamadas, consultorías, podcasts o directos, con el problema, la explicación y su solución. Puede añadir capturas reales y un cierre con tu recurso.
- **Tu perfil de canal:** audiencia, estilo, voces, permisos y carpeta de entrega. Puedes tener varios canales sin mezclar sus estilos.
- **Studio Local, opcional:** un editor visual para revisar y retocar el montaje, dejar comentarios sobre un fotograma y pedir a la IA que los aplique. Las skills también funcionan sin él.
- **Entrega:** vídeos en una carpeta del Mac; si lo eliges y conectas tu cuenta, también en Drive, repartidos por días.

Solo para **macOS**. La edición con clipkit está comprobada en Apple Silicon; los Mac Intel usan otro transcriptor y requieren su propia prueba. Studio Local actualmente requiere **M1 o posterior**. Windows y Linux quedan fuera de esta versión.

La IA necesita leer y escribir archivos y ejecutar programas **en tu Mac**: adjuntarlo a un chat web sin esas herramientas no instala nada. Otro agente con esas capacidades puede seguir el mismo archivo, aunque debe comprobar dónde carga sus skills.

La transcripción y el render se ejecutan localmente, sin una API de pago de vídeo. Tu asistente puede procesar los textos e imágenes que lea según su servicio; «local» no significa que el chat sea offline. Drive solo se utiliza si lo eliges. La instalación necesita internet y varios GB para herramientas y modelos; tus vídeos pueden ocupar mucho más.

Después podrás decir: «haz clips de esta grabación», «clip del 12:30 al 14:05», «saca mids de esta llamada», «cambia los subtítulos a amarillo» o, con Studio, «aplica mis comentarios».

## Para el agente · acompañar la instalación

Completa extracción → herramientas → canal → editor opcional → prueba → entrega. Explica el propósito de cada paso en una frase. No vuelques este documento ni su código en el chat. No declares que está listo solo porque copiaste las skills.

### 1. Comprobar equipo y agente

Comprueba `sw_vers -productVersion`, `uname -m`, Python y las capacidades reales de la sesión: archivos locales, ejecución y lectura de imágenes. En un chat web o una sesión remota sin acceso al Mac, explica cómo abrir el agente en modo local y deja pendiente la instalación. No la simules en un contenedor remoto. Fuera de macOS, detente antes de instalar.

Si falta Python, comprueba las herramientas de Apple con `xcode-select -p`; ofrece instalarlas con `xcode-select --install` y espera a que el usuario complete el diálogo. Nunca pidas contraseñas en el chat ni cambies protecciones del Mac.

Elige la carpeta que cargue el agente, sin duplicar skills:

- Claude Code local: `~/.claude/skills/`, según su [documentación](https://code.claude.com/docs/en/skills).
- Codex actual: `~/.agents/skills/`, según su [documentación](https://developers.openai.com/codex/skills/). En una versión que documente otra ruta, usa la que efectivamente cargue; algunas instalaciones anteriores usan `~/.codex/skills/` o `$CODEX_HOME/skills/`.
- Otro agente: comprueba su mecanismo documentado. Si no carga skills, puede leer los manuales durante la sesión; explica que eso no equivale a instalarlas en su catálogo.

Usa el agente que ejecuta el encargo; solo pregunta por instalar también en otro si el usuario quiere ambos. No instales ni autentiques un asistente nuevo por tu cuenta.

### 2. Extraer el paquete

El documento contiene siete recursos completos y sus huellas. Guarda el siguiente extractor en un temporal y ejecútalo con **la ruta de este documento** y **la carpeta de skills**. Para Claude, por ejemplo:

```bash
python3 extraer.py "/ruta/Clips verticales y mids · instalador.md" "$HOME/.claude/skills" --plan
python3 extraer.py "/ruta/Clips verticales y mids · instalador.md" "$HOME/.claude/skills"
```

La petición de instalar autoriza la extracción y las dependencias que hayas explicado dentro de ese alcance. Respeta los permisos del entorno; no pidas otra aprobación para cada archivo. Con versiones distintas, compara antes y pide una sola aprobación para sustituirlas. `--actualizar` guarda copia en `~/ClipsYMids/versiones-anteriores/`. Los canales y trabajos quedan intactos. Una huella incorrecta o un paquete incompleto bloquea todas las escrituras: descarga el original de nuevo.

Las huellas detectan corrupción accidental; no prueban la autoría. Ejecuta solo el paquete obtenido del origen elegido por el usuario.

```python
#!/usr/bin/env python3
"""Extrae el paquete completo antes de escribir; conserva las versiones sustituidas."""
import argparse
import datetime
import hashlib
import os
from pathlib import Path
import re
import tempfile

TOOLS = {"clipkit.py", "CONFIGURAR.md", "CORTES.md", "STUDIO.md"}
SKILLS = {"maquina-contenido", "clips-verticales", "mids-desde-grabaciones"}


def plan(document, skills, tools):
    document = document.replace("\r\n", "\n")
    rows = re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$", document, re.M)
    blocks = re.findall(r"^### `([^`]+)`\n+~~~~~[a-z]*\n(.*?)\n~~~~~$", document, re.S | re.M)
    expected = {"~/ClipsYMids/" + name for name in TOOLS}
    expected |= {"<skills>/" + name + "/SKILL.md" for name in SKILLS}
    if (len(rows) != len(expected) or len(blocks) != len(expected)
            or {x[0] for x in rows} != expected or {x[0] for x in blocks} != expected):
        raise ValueError("Paquete incompleto, repetido o con destinos desconocidos; no se ha escrito nada.")
    hashes = dict(rows)
    result = []
    for name, body in blocks:
        data = (body + "\n").encode("utf-8")
        if hashlib.sha256(data).hexdigest() != hashes[name]:
            raise ValueError(name + ": huella incorrecta; descarga de nuevo el archivo original.")
        root, relative = (skills, name[len("<skills>/"):]) if name.startswith("<skills>/") else (tools, name[len("~/ClipsYMids/"):])
        root = root.expanduser().resolve()
        destination = root / relative
        if destination.is_symlink() or root not in destination.resolve().parents:
            raise ValueError(name + ": destino enlazado fuera de su carpeta; no se ha escrito nada.")
        if destination.exists() and not destination.is_file():
            raise ValueError(str(destination) + ": no es un archivo.")
        old = destination.read_bytes() if destination.exists() else None
        result.append((name, destination, data, old))
    return result


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".instalar-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(document, skills, tools, update=False, dry_run=False):
    entries = plan(document, skills, tools)
    changed = [x for x in entries if x[2] != x[3]]
    conflicts = [str(x[1]) for x in changed if x[3] is not None]
    if dry_run:
        return {"escrituras": [str(x[1]) for x in changed], "sustituciones": conflicts}
    if conflicts and not update:
        raise ValueError("Hay versiones distintas. No se ha escrito nada. Revisa las diferencias y usa --actualizar si el usuario autoriza sustituirlas:\n" + "\n".join(conflicts))
    backup = None
    if conflicts:
        backups = tools.expanduser().resolve() / "versiones-anteriores"
        backups.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-")
        backup = Path(tempfile.mkdtemp(prefix=stamp, dir=backups))
        for name, _, _, old in changed:
            if old is not None:
                relative = name.replace("~/ClipsYMids/", "herramientas/").replace("<skills>/", "skills/")
                atomic(backup / relative, old)
    written = []
    try:
        for entry in changed:
            written.append(entry)
            atomic(entry[1], entry[2])
        for _, destination, data, _ in entries:
            if destination.read_bytes() != data:
                raise OSError("No coincide la lectura de " + str(destination))
    except Exception:
        for _, destination, _, old in reversed(written):
            if old is None:
                destination.unlink(missing_ok=True)
            else:
                atomic(destination, old)
        raise
    return {"verificados": len(entries), "escritos": len(changed), "copia_anterior": str(backup) if backup else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instalador", type=Path)
    parser.add_argument("skills", type=Path)
    parser.add_argument("--plan", action="store_true", help="comprobar sin escribir")
    parser.add_argument("--actualizar", action="store_true", help="sustituir versiones distintas conservando una copia")
    args = parser.parse_args()
    try:
        if os.uname().sysname != "Darwin":
            raise ValueError("Esta versión del instalador es solo para Mac.")
        result = install(args.instalador.read_text(encoding="utf-8"), args.skills, Path("~/ClipsYMids"), args.actualizar, args.plan)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

Antes de descargar el editor, comprueba si el documento viene junto a un repositorio local: `studio-local/ONBOARDING.md` al lado del archivo, o `../ONBOARDING.md` si está en `contenido/` dentro del repositorio. Guarda esa ruta como `editor_incluido` en el estado de instalación y sigue `STUDIO.md`; no hagas una segunda descarga.

Tras extraer, lee `maquina-contenido/SKILL.md` y continúa sin pedir al usuario que invoque otra skill. Guarda el avance en `~/ClipsYMids/instalacion.json` después de cada fase: versión, carpeta de skills, herramientas comprobadas, canal activo, editor elegido y ruta, pruebas y pendientes. Sin credenciales. Reanuda contrastando el estado con los programas y archivos reales.

### 3. Preparar las herramientas

Explica: «Voy a preparar las herramientas que cortan el vídeo y convierten tu voz en texto para poder editarlo».

Ejecuta `python3 ~/ClipsYMids/clipkit.py entorno` y resuelve solo lo que falte:

- **Python:** usa 3.10 o posterior para los motores actuales y un entorno propio `~/ClipsYMids/venv`; no cambies el Python del sistema.
- **FFmpeg:** comprueba ffmpeg, ffprobe, libass y libx264. Si faltan, usa Homebrew existente y `brew install ffmpeg-full`. Sin Homebrew, explica esa instalación adicional y pide la elección antes de seguir su [instalador oficial](https://brew.sh/). No sustituyas versiones existentes a ciegas. Para rutas propias, clipkit acepta `CLIPKIT_FFMPEG` y `CLIPKIT_FFPROBE`.
- **Transcripción:** Apple Silicon: `mlx-whisper` con `mlx-community/whisper-large-v3-turbo`; Intel: `faster-whisper` con `small` como punto de partida. Reutiliza un motor funcional o instala el elegido en el entorno propio: `python3 -m venv ~/ClipsYMids/venv`, después su `bin/python -m pip install mlx-whisper` o `faster-whisper`. La primera transcripción descarga el modelo: avisa del espacio y la conexión antes de empezar.

Repite `entorno --python ~/ClipsYMids/venv/bin/python` y, con `listo_para_render` verdadero, `entorno --guardar`. Guarda el Python y modelo reales en el perfil. Detectar un módulo no prueba que transcriba: se verifica con el vídeo en el paso 6.

### 4. Conocer el canal

Sigue `~/ClipsYMids/CONFIGURAR.md`. Explica qué información sirve para seleccionar momentos y cuál para su aspecto visual. Pregunta solo las rondas de los formatos elegidos, acepta recomendaciones y guarda lo respondido para no repetir preguntas al retomar.

### 5. Ofrecer Studio Local

Explica las funciones y la diferencia entre un proyecto de clipkit y un montaje visual según `~/ClipsYMids/STUDIO.md`. Pregunta si quiere instalarlo ahora, reutilizar el que ya tiene o continuar sin él. Espera su respuesta. En Intel, explica su límite y continúa con clipkit.

Si lo elige, sigue `STUDIO.md`, comprueba el editor y guarda su ruta real en el perfil. La interfaz móvil y el acceso remoto son opciones posteriores, no requisitos del onboarding.

### 6. Hacer la primera pieza

Usa una grabación real del usuario. Sin vídeo, termina como **herramientas instaladas; primera prueba pendiente** y dile qué archivo traer. No afirmes que su estilo está aprobado ni que funciona con sus vídeos.

Con vídeo, comprueba duración y elige una frase completa corta dentro de ella; transcríbela y lee el resultado. Sin tramo indicado, propón uno y acepta su elección. Genera una muestra de cada formato elegido según `CONFIGURAR.md`, mírala y enséñala para ajustar el estilo. Tras su aprobación, edita una pieza corta, renderiza y verifica audio, imagen, textos y duración con la skill correspondiente. Con Studio, crea también el proyecto nativo y enséñalo en la app: un MP4 importado como único clip no es un montaje editable con textos.

### 7. Cerrar el onboarding

Entrega qué quedó instalado, dónde, canal y estilo, prueba visible y pendientes. Enséñale tres peticiones útiles para su caso. Con Studio, explica Espacio, ⌘Z y ⌘F. Verifica que el agente reconoce las tres skills; si no, comprueba la ruta y reinicia la sesión solo cuando haga falta.

Instalar no autoriza publicar, conectar cuentas nuevas, subir material, comprar servicios ni limpiar fuentes. Conserva la primera prueba para revisión; Drive, calendario y limpieza recuperable se ejecutan cuando el usuario los pida.

## Huellas

| Archivo | SHA-256 |
| --- | --- |
| `~/ClipsYMids/clipkit.py` | `3e00a3dfb2b4b522e853c062748f6e4841df73ff748b98dc9658b9c65a39254f` |
| `~/ClipsYMids/CONFIGURAR.md` | `599b07328a87f08322e9fa95d637db646d58f51d12ede6822e1f48590f38c838` |
| `~/ClipsYMids/CORTES.md` | `907a0bea55a337c39574ce9d158763f369a8764d8a97039e419fcc5d5108365b` |
| `~/ClipsYMids/STUDIO.md` | `3b9b683fbb5cb176e62625e1f1f62fbac42a4ee9e97409122642de3ba3f1b51d` |
| `<skills>/maquina-contenido/SKILL.md` | `42ce7703c1cab7df499d9395e331204c5ec63feb980ef284668d949dd45184e6` |
| `<skills>/clips-verticales/SKILL.md` | `c2695759b962d4ee45f59847a12cf51c14520592e153948ed7092aac557bfcba` |
| `<skills>/mids-desde-grabaciones/SKILL.md` | `b2ace79875279bbaea05c3edfe7c2fa9741dd2e6c9cecce0736460f8941d39f1` |

## Archivos

### `~/ClipsYMids/clipkit.py`

~~~~~python
#!/usr/bin/env python3
"""clipkit: cortes, subtitulos y render de clips verticales y mids con ffmpeg.

Ordenes (python3 clipkit.py <orden> -h para el detalle):
  entorno      comprueba ffmpeg, libass y motores de transcripcion
  transcribir  audio -> palabras con tiempos (JSON)
  leer         transcripcion legible con tiempos, o --buscar una frase
  bordes       energia de la voz alrededor de un punto de corte
  subtitulos   genera subtitulos.json editable de un trabajo
  render       renderiza un trabajo (clip o mid) o un fotograma con --muestra
  verificar    decodificacion completa, formato, sonoridad y hoja de fotogramas
  fuentes      nombres de familia de las fuentes de una carpeta
  fotograma    extrae un fotograma de la fuente
  muestra      fotograma de prueba del estilo de un perfil

Solo biblioteca estandar + ffmpeg/ffprobe; para transcribir, un motor Whisper
(mlx-whisper, faster-whisper u openai-whisper) en este Python o en otro (--python).
"""
from __future__ import annotations

import argparse
import array
import copy
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

VERSION = "2.0"

DEFAULTS = {
    "fuentes_dir": None,
    "clips": {
        "lienzo": [1080, 1920],
        "encuadre": "completo",          # completo | recorte | pila | vertical
        "margen_video": 44,
        "fondo": {"tipo": "color", "color": "#000000"},   # color | desenfoque
        "gancho": {
            "activo": True,
            "texto_defecto": "Escribe aquí\ntu gancho",
            "estilo": "editorial",       # editorial | caja | simple
            "fuente": "Helvetica Neue",
            "tamano": 70,
            "color": "#FFFFFF",
            "acento": "#B28CFF",
            "caja": "#000000",
            "mayusculas": False,
            "duracion": None,            # None = todo el clip; o segundos
        },
        "subtitulos": {
            "activo": True,
            "modo": "palabra",           # palabra | resaltado | frase
            "fuente": "Helvetica Neue",
            "tamano": 62,
            "negrita": True,
            "color": "#FFFFFF",
            "enfasis": "#B28CFF",
            "mayusculas": False,
            "posicion": "auto",          # auto | bajo_video | inferior | centro | superior
            "max_lineas": 2,
            "max_caracteres": 24,
            "contorno": 0,
            "sombra": 2,
        },
        "logo": None,                    # {"archivo": ruta, "esquina": "sup_der", "ancho": 120, "opacidad": 0.9}
    },
    "mids": {
        "lienzo": [1920, 1080],
        "subtitulos": {
            "cuando": "invitado",        # nunca | invitado | siempre
            "modo": "frase",
            "fuente": "Helvetica Neue",
            "tamano": 64,
            "negrita": True,
            "color": "#FFFFFF",
            "enfasis": "#FFFFFF",
            "mayusculas": False,
            "posicion": "inferior",
            "max_lineas": 1,
            "max_caracteres": 44,
            "contorno": 2,
            "sombra": 2,
        },
        "logo": None,
    },
    "sonido": {"lufs": -14.0, "pico": -1.0},   # null = no normalizar
    "video": {"codificador": "libx264", "crf": 18, "preset": "medium"},
}

SAMPLE_WORDS = "Así se ve tu palabra destacada".split()


# ---------------------------------------------------------------- utilidades

def die(msg: str) -> None:
    sys.stderr.write(f"clipkit: {msg}\n")
    raise SystemExit(1)


CONFIG_PATH = Path(__file__).resolve().with_name("config.json")
KEG_FFMPEG = ("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg", "/usr/local/opt/ffmpeg-full/bin/ffmpeg")
_CACHE = {}


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ff_features(ff):
    key = ("feat", ff)
    if key not in _CACHE:
        filt = run([ff, "-hide_banner", "-filters"], check=False).stdout
        enc = run([ff, "-hide_banner", "-encoders"], check=False).stdout
        _CACHE[key] = {"libass": bool(re.search(r"\sass\s", filt)), "zscale": bool(re.search(r"\szscale\s", filt)),
                       "loudnorm": "loudnorm" in filt, "libx264": "libx264" in enc,
                       "videotoolbox": "h264_videotoolbox" in enc}
    return _CACHE[key]


def ffmpeg_bin() -> str:
    """CLIPKIT_FFMPEG > config.json > ffmpeg-full de Homebrew > ffmpeg del PATH (el primero con libass)."""
    if "ff" in _CACHE:
        return _CACHE["ff"]
    explicit = os.environ.get("CLIPKIT_FFMPEG") or load_config().get("ffmpeg")
    if explicit:
        ff = explicit if os.path.exists(explicit) else shutil.which(explicit)
        if not ff:
            die(f"no existe el ffmpeg configurado: {explicit}")
    else:
        cands = [c for c in (*KEG_FFMPEG, shutil.which("ffmpeg")) if c and os.path.exists(c)]
        if not cands:
            die("no encuentro ffmpeg (instálalo o define CLIPKIT_FFMPEG)")
        ff = next((c for c in cands if ff_features(c)["libass"]), cands[0])
    _CACHE["ff"] = ff
    return ff


def ffprobe_bin():
    explicit = os.environ.get("CLIPKIT_FFPROBE") or load_config().get("ffprobe")
    if explicit:
        return explicit
    ff = Path(ffmpeg_bin())
    sib = ff.with_name("ffprobe" + (".exe" if ff.suffix.lower() == ".exe" else ""))
    return str(sib) if sib.exists() else shutil.which("ffprobe")


def run(cmd, check=True, cwd=None):
    p = subprocess.run([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, errors="replace", cwd=cwd)
    if check and p.returncode != 0:
        sys.stderr.write(p.stderr[-3000:] + "\n")
        die(f"falló {Path(str(cmd[0])).name} (código {p.returncode})")
    return p


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_profile(path):
    data = load_json(path) if path else {}
    prof = deep_merge(DEFAULTS, data)
    fd = prof.get("fuentes_dir")
    if fd:
        fd = Path(os.path.expanduser(fd))
        if not fd.is_absolute() and path:
            fd = Path(path).parent / fd
        prof["fuentes_dir"] = str(fd)
    return prof


def resolve(base: Path, p):
    if p is None:
        return None
    q = Path(os.path.expanduser(str(p)))
    return q if q.is_absolute() else (base / q)


def fmt_ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}" if h else f"{m:02d}:{s:05.2f}"


def ass_ts(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def even(x: float) -> int:
    return int(round(x / 2.0)) * 2


def norm_word(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]", "", s)


def fps_value(fps: str) -> float:
    if "/" in fps:
        a, b = fps.split("/")
        return float(a) / float(b) if float(b) else 30.0
    return float(fps)


def fps_fraction(v: float) -> str:
    for frac in ("24000/1001", "30000/1001", "60000/1001"):
        if abs(fps_value(frac) - v) < 0.01:
            return frac
    return str(int(round(v))) if abs(v - round(v)) < 0.01 else f"{v:.3f}"


# ---------------------------------------------------------------- probe

def probe(path) -> dict:
    path = str(path)
    if not os.path.exists(path):
        die(f"no existe {path}")
    ffprobe = ffprobe_bin()
    if ffprobe:
        p = run([ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path])
        d = json.loads(p.stdout)
        streams = d.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)
        info = {"duracion": float(d.get("format", {}).get("duration") or 0), "audio": a is not None}
        if v:
            w, h = int(v["width"]), int(v["height"])
            rot = 0
            for sd in v.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rot = int(float(sd["rotation"]))
            rot = rot or int(float(v.get("tags", {}).get("rotate", 0) or 0))
            if abs(rot) % 180 == 90:
                w, h = h, w
            fr = v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1"
            if fr in ("0/0", "0/1"):
                fr = v.get("r_frame_rate") or "30/1"
            info.update(ancho=w, alto=h, fps=fps_fraction(fps_value(fr)), pix_fmt=v.get("pix_fmt"),
                        trc=v.get("color_transfer"), primarias=v.get("color_primaries"), matriz=v.get("color_space"))
        return info
    p = run([ffmpeg_bin(), "-hide_banner", "-i", path], check=False)
    err = p.stderr
    info = {"duracion": 0.0, "audio": bool(re.search(r"Stream #.*Audio:", err))}
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        info["duracion"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    vline = next((ln for ln in err.splitlines() if re.search(r"Stream #.*Video:", ln)
                  and "attached pic" not in ln), None)
    if vline:
        mm = re.search(r"\b(\d{2,5})x(\d{2,5})\b", vline)
        w, h = int(mm.group(1)), int(mm.group(2))
        if re.search(r"rotation of -?(90|270)\.00", err):
            w, h = h, w
        ff = re.search(r"(\d+(?:\.\d+)?) fps", vline) or re.search(r"(\d+(?:\.\d+)?) tbr", vline)
        info.update(ancho=w, alto=h, fps=fps_fraction(float(ff.group(1)) if ff else 30.0))
        pm = re.search(r"Video: .*?, (\w+)\(([^)]*)\)", vline)
        if pm:
            info["pix_fmt"] = pm.group(1)
            for part in pm.group(2).split(", "):
                bits = part.split("/")
                if len(bits) == 3:
                    info.update(matriz=bits[0], primarias=bits[1], trc=bits[2])
                elif part in ("bt709", "bt2020nc", "bt470bg", "smpte170m"):
                    info.update(matriz=part, primarias="bt2020" if part.startswith("bt2020") else part,
                                trc=part)
    return info


# ---------------------------------------------------------------- entorno

def cmd_entorno(a):
    res = {"version": VERSION, "python": sys.executable, "plataforma": platform.platform(),
           "apple_silicon": platform.system() == "Darwin" and platform.machine() == "arm64"}
    try:
        ff = ffmpeg_bin()
    except SystemExit:
        ff = None
    res["ffmpeg"] = ff
    if ff:
        res["ffmpeg_version"] = run([ff, "-hide_banner", "-version"], check=False).stdout.splitlines()[0]
        res.update(ff_features(ff))
        res["ffprobe"] = ffprobe_bin()
        if not res["libass"]:
            res["consejo"] = "este ffmpeg no tiene libass: en Mac instala `brew install ffmpeg-full`"
    pythons = [sys.executable] + list(a.python or [])
    motores = {}
    for py in pythons:
        for mod in ("mlx_whisper", "faster_whisper", "whisper"):
            p = run([py, "-c", f"import {mod}"], check=False)
            if p.returncode == 0:
                motores.setdefault(mod, py)
    res["motores"] = motores
    falta = [k for k in ("ffmpeg", "libass", "libx264") if not res.get(k)]
    res["listo_para_render"] = not falta
    res["listo_para_transcribir"] = bool(motores)
    if a.guardar and res["listo_para_render"]:
        cfg = load_config()
        cfg.update(ffmpeg=ff, ffprobe=res.get("ffprobe"))
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        res["guardado_en"] = str(CONFIG_PATH)
    print(json.dumps(res, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- transcribir

def _load_wav_np(path):
    import wave
    import numpy as np
    with wave.open(path) as w:
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, np.int16).astype(np.float32) / 32768.0


def cmd_motor(a):
    """Orden interna: ejecuta el motor en este Python y escribe palabras crudas."""
    audio = _load_wav_np(a.wav)
    words = []
    lang = a.idioma or None
    if a.motor == "mlx_whisper":
        import mlx_whisper
        r = mlx_whisper.transcribe(audio, path_or_hf_repo=a.modelo or "mlx-community/whisper-large-v3-turbo",
                                   language=lang, word_timestamps=True)
        for seg in r.get("segments", []):
            for w in seg.get("words", []):
                words.append((w["word"], w["start"], w["end"]))
    elif a.motor == "faster_whisper":
        from faster_whisper import WhisperModel
        model = WhisperModel(a.modelo or "small", device="auto", compute_type="int8")
        segs, _ = model.transcribe(audio, language=lang, word_timestamps=True, beam_size=5)
        for seg in segs:
            for w in seg.words or []:
                words.append((w.word, w.start, w.end))
    elif a.motor == "whisper":
        import whisper
        model = whisper.load_model(a.modelo or "small")
        r = model.transcribe(audio, language=lang, word_timestamps=True)
        for seg in r.get("segments", []):
            for w in seg.get("words", []):
                words.append((w["word"], w["start"], w["end"]))
    else:
        die(f"motor desconocido {a.motor}")
    save_json(a.salida, [{"texto": t.strip(), "inicio": round(float(s), 3), "fin": round(float(e), 3)}
                         for t, s, e in words if t.strip()])


def detect_engine(pythons):
    order = ["mlx_whisper", "faster_whisper", "whisper"]
    if not (platform.system() == "Darwin" and platform.machine() == "arm64"):
        order = ["faster_whisper", "whisper", "mlx_whisper"]
    for mod in order:
        for py in pythons:
            if run([py, "-c", f"import {mod}"], check=False).returncode == 0:
                return mod, py
    die("no hay motor de transcripción (instala mlx-whisper o faster-whisper)")


def cmd_transcribir(a):
    medio = Path(a.medio).expanduser()
    info = probe(medio)
    if not info["audio"]:
        die("el medio no tiene audio")
    py = a.python or sys.executable
    motor = a.motor
    if motor in (None, "auto"):
        motor, py = detect_engine([py])
    tmp = Path(tempfile.mkdtemp(prefix="clipkit_"))
    try:
        wav = tmp / "audio.wav"
        cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y"]
        if a.desde is not None:
            cmd += ["-ss", f"{a.desde:.3f}"]
        if a.hasta is not None:
            cmd += ["-t", f"{a.hasta - (a.desde or 0):.3f}"]
        cmd += ["-i", str(medio), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
        run(cmd)
        raw = tmp / "raw.json"
        args = [py, os.path.abspath(__file__), "_motor", str(wav), str(raw), "--motor", motor]
        if a.modelo:
            args += ["--modelo", a.modelo]
        if a.idioma:
            args += ["--idioma", a.idioma]
        p = subprocess.run(args)
        if p.returncode != 0 or not raw.exists():
            die("el motor de transcripción falló")
        off = a.desde or 0.0
        words = [{"texto": w["texto"], "inicio": round(w["inicio"] + off, 3), "fin": round(w["fin"] + off, 3)}
                 for w in load_json(raw)]
        out = {"version": 1, "medio": str(medio.resolve()), "motor": motor, "modelo": a.modelo,
               "idioma": a.idioma, "desde": a.desde, "hasta": a.hasta, "palabras": words}
        save_json(a.salida, out)
        print(json.dumps({"salida": str(a.salida), "palabras": len(words), "motor": motor}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- leer / buscar

def load_words(path):
    d = load_json(path)
    return d["palabras"] if isinstance(d, dict) else d


def cmd_leer(a):
    ws = load_words(a.palabras)
    if a.desde is not None:
        ws = [w for w in ws if w["fin"] >= a.desde]
    if a.hasta is not None:
        ws = [w for w in ws if w["inicio"] <= a.hasta]
    if a.buscar:
        target = [norm_word(t) for t in a.buscar.split() if norm_word(t)]
        toks = [norm_word(w["texto"]) for w in ws]
        found = []
        for i in range(len(ws) - len(target) + 1):
            if toks[i:i + len(target)] == target:
                j = i + len(target) - 1
                prev_end = ws[i - 1]["fin"] if i > 0 else ws[i]["inicio"]
                next_start = ws[j + 1]["inicio"] if j + 1 < len(ws) else ws[j]["fin"]
                found.append({"inicio": ws[i]["inicio"], "fin": ws[j]["fin"],
                              "corte_antes": round((prev_end + ws[i]["inicio"]) / 2, 3),
                              "corte_despues": round((ws[j]["fin"] + next_start) / 2, 3),
                              "contexto": " ".join(w["texto"] for w in ws[max(0, i - 6):j + 7])})
        print(json.dumps(found, ensure_ascii=False, indent=2))
        return
    line, start, prev = [], None, None
    for w in ws:
        brk = prev is not None and (w["inicio"] - prev["fin"] > a.pausa
                                    or prev["texto"][-1:] in ".?!…"
                                    or sum(len(x) + 1 for x in line) > 100)
        if brk and line:
            print(f"[{fmt_ts(start)}] {' '.join(line)}")
            line = []
        if not line:
            start = w["inicio"]
        line.append(w["texto"])
        prev = w
    if line:
        print(f"[{fmt_ts(start)}] {' '.join(line)}")


# ---------------------------------------------------------------- bordes

def cmd_bordes(a):
    res = []
    for t in a.tiempos:
        s = max(0.0, t - a.ventana)
        p = subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-ss", f"{s:.3f}",
                            "-t", f"{t + a.ventana - s:.3f}", "-i", str(a.medio), "-vn", "-ac", "1",
                            "-ar", "16000", "-f", "s16le", "-"], stdout=subprocess.PIPE)
        samples = array.array("h")
        samples.frombytes(p.stdout[: len(p.stdout) // 2 * 2])
        hop = 80  # 5 ms
        frames = []
        for i in range(0, len(samples) - hop + 1, hop):
            chunk = samples[i:i + hop]
            rms = math.sqrt(sum(x * x for x in chunk) / hop) / 32768.0
            frames.append((round(s + i / 16000.0, 3), round(20 * math.log10(rms + 1e-9), 1)))
        if not frames:
            res.append({"t": t, "error": "sin audio en la ventana"})
            continue
        tmin, dmin = min(frames, key=lambda f: (f[1], abs(f[0] - t)))
        silent = [f for f in frames if f[1] <= a.umbral]
        near = min(silent, key=lambda f: abs(f[0] - t)) if silent else None
        at_t = min(frames, key=lambda f: abs(f[0] - t))
        perfil = [round(sum(f[1] for f in frames[i:i + 2]) / len(frames[i:i + 2])) for i in range(0, len(frames), 2)]
        res.append({"t": t, "db_en_t": at_t[1],
                    "minimo": {"t": tmin, "db": dmin},
                    "silencio_mas_cercano": {"t": near[0], "db": near[1]} if near else None,
                    "perfil_db_10ms_desde": round(s, 3), "perfil_db_10ms": perfil})
    print(json.dumps(res, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- trabajos

def load_job(path):
    path = Path(path).expanduser().resolve()
    job = load_json(path)
    base = path.parent
    job["_dir"] = base
    job["_path"] = path
    for k in ("fuente", "palabras", "perfil", "gancho_video", "cta_video", "salida"):
        if job.get(k):
            job[k] = str(resolve(base, job[k]))
    for ins in job.get("inserciones", []) or []:
        ins["imagen"] = str(resolve(base, ins["imagen"]))
    tramos = []
    for t in job.get("tramos", []):
        if isinstance(t, dict):
            tr = dict(t)
        else:
            tr = {"inicio": float(t[0]), "fin": float(t[1])}
        if tr["fin"] <= tr["inicio"]:
            die(f"tramo invertido o vacío: {t}")
        tramos.append(tr)
    if not tramos:
        die("el trabajo no tiene tramos")
    job["tramos"] = tramos
    if isinstance(job.get("encuadre"), str):
        job["encuadre"] = {"tipo": job["encuadre"]}
    if isinstance(job.get("gancho"), str):
        job["gancho"] = {"texto": job["gancho"]}
    if job.get("tipo") not in ("clip", "mid"):
        die("el trabajo necesita \"tipo\": \"clip\" o \"mid\"")
    return job


def map_words(words, tramos, rangos=None):
    out, off = [], 0.0
    for tr in tramos:
        s, e = tr["inicio"], tr["fin"]
        for w in words:
            mid = (w["inicio"] + w["fin"]) / 2
            if s <= mid <= e and (not rangos or any(r0 <= mid <= r1 for r0, r1 in rangos)):
                out.append({"texto": w["texto"], "inicio": round(max(w["inicio"], s) - s + off, 3),
                            "fin": round(min(w["fin"], e) - s + off, 3), "enfasis": False})
        off += e - s
    return out


def text_len(ws):
    return sum(len(w["texto"]) for w in ws) + max(0, len(ws) - 1)


def make_blocks(ws, max_chars, max_lines, gap=0.45):
    cap = max_chars * max_lines
    blocks, cur = [], []
    for w in ws:
        if cur:
            prev = cur[-1]["texto"].rstrip()
            if (w["inicio"] - cur[-1]["fin"] > gap or text_len(cur + [w]) > cap
                    or prev[-1:] in ".?!…" or (prev[-1:] in ",;:" and text_len(cur) >= cap * 0.5)):
                blocks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        blocks.append(cur)
    return blocks


def cmd_subtitulos(a):
    job = load_job(a.trabajo)
    prof = load_profile(job.get("perfil"))
    sec = prof["clips" if job["tipo"] == "clip" else "mids"]["subtitulos"]
    if not job.get("palabras"):
        die("el trabajo no indica \"palabras\" (transcripción de la fuente)")
    rangos = job.get("subtitulos_en")
    if job["tipo"] == "mid" and sec.get("cuando") == "nunca" and not rangos:
        die("el perfil dice subtítulos \"nunca\" en mids; añade \"subtitulos_en\" al trabajo si los quieres")
    if job["tipo"] == "mid" and sec.get("cuando") == "invitado" and not rangos:
        die("perfil con subtítulos solo del invitado: indica sus tramos en \"subtitulos_en\" (tiempos de la fuente)")
    snap_tramos(job["tramos"], probe(job["fuente"]).get("fps", "30"))
    ws = map_words(load_words(job["palabras"]), job["tramos"], rangos)
    blocks = make_blocks(ws, int(sec["max_caracteres"]), int(sec["max_lineas"]))
    out = Path(a.salida) if a.salida else job["_dir"] / "subtitulos.json"
    if out.exists() and not a.forzar:
        die(f"{out} ya existe (usa --forzar para regenerarlo y perder sus correcciones)")
    save_json(out, {"bloques": [{"palabras": b} for b in blocks]})
    print(json.dumps({"salida": str(out), "bloques": len(blocks), "palabras": len(ws)}, ensure_ascii=False))


# ---------------------------------------------------------------- ASS

def ass_col(hexstr, alpha=0):
    h = hexstr.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ass_inline(hexstr):
    h = hexstr.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def ass_escape(s):
    return s.replace("\\", "/").replace("{", "(").replace("}", ")")


def wrap_lines(texts, max_chars, max_lines):
    n = len(texts)

    def L(i, j):
        return sum(len(t) for t in texts[i:j]) + max(0, j - i - 1)

    if n == 0:
        return []
    if L(0, n) <= max_chars or max_lines <= 1:
        return [(0, n)]
    if max_lines == 2 or L(0, n) <= 2 * max_chars:
        best = None
        for k in range(1, n):
            a, b = L(0, k), L(k, n)
            if max(a, b) <= max_chars:
                score = abs(a - b)
                if best is None or score < best[0]:
                    best = (score, k)
        if best:
            return [(0, best[1]), (best[1], n)]
    lines_needed = min(max_lines, max(2, math.ceil(L(0, n) / max_chars)))
    target = L(0, n) / lines_needed
    lines, start = [], 0
    for i in range(1, n + 1):
        if len(lines) < lines_needed - 1 and i < n and L(start, i + 1) > max(target, 1) and L(start, i) > 0:
            if L(start, i + 1) > max_chars or L(start, i) >= target:
                lines.append((start, i))
                start = i
    lines.append((start, n))
    return lines


def style_line(name, font, size, color, bold, italic=False, outline=0.0, shadow=0.0,
               outline_col="#000000", back_col="#000000", back_alpha=0x80, border_style=1, align=2):
    return ("Style: {n},{f},{s},{pc},&H000000FF,{oc},{bc},{b},{i},0,0,100,100,0,0,{bs},{o},{sh},{al},0,0,0,1"
            .format(n=name, f=font, s=size, pc=ass_col(color), oc=ass_col(outline_col),
                    bc=ass_col(back_col, back_alpha), b=-1 if bold else 0, i=-1 if italic else 0,
                    bs=border_style, o=outline, sh=shadow, al=align))


def caption_events(blocks, sec, an, x, y, offset=0.0, hold=0.5):
    """Eventos de subtítulos. Composición estable: el bloque entero se maqueta desde
    el principio y las palabras futuras quedan transparentes."""
    color, accent = sec["color"], sec["enfasis"]
    sh_alpha = 0x80
    vis = "\\1a&H00&\\3a&H00&\\4a&H{:02X}&".format(sh_alpha)
    inv = "\\1a&HFF&\\3a&HFF&\\4a&HFF&"
    fade = "\\1a&HFF&\\3a&HFF&\\4a&HFF&\\t(0,90,\\1a&H00&\\3a&H00&\\4a&H{:02X}&)".format(sh_alpha)
    mode = sec.get("modo", "palabra")
    upper = sec.get("mayusculas")
    events = []
    clean = [b for b in blocks if b.get("palabras")]
    for bi, b in enumerate(clean):
        ws = b["palabras"]
        texts = [(w["texto"].upper() if upper else w["texto"]) for w in ws]
        lines = wrap_lines(texts, int(sec["max_caracteres"]), int(sec["max_lineas"]))
        start = ws[0]["inicio"]
        end = ws[-1]["fin"] + hold
        if bi + 1 < len(clean):
            end = min(end, clean[bi + 1]["palabras"][0]["inicio"])
        end = max(end, ws[-1]["fin"], start + 0.2)

        def render(state_k):
            parts = []
            for li, (i0, i1) in enumerate(lines):
                seg = []
                for j in range(i0, i1):
                    w = ws[j]
                    if mode == "resaltado":
                        col = accent if j == state_k else color
                        tag = vis
                    elif mode == "frase":
                        col = accent if w.get("enfasis") else color
                        tag = vis
                    else:
                        col = accent if w.get("enfasis") else color
                        tag = vis if j < state_k else (fade if j == state_k else inv)
                    seg.append("{" + tag + "\\c" + ass_inline(col) + "}" + ass_escape(texts[j]))
                parts.append(" ".join(seg))
            return "{\\" + an + "\\pos(" + f"{x:.0f},{y:.0f}" + ")}" + "\\N".join(parts)

        if mode == "frase":
            events.append((start, end, render(-1)))
            continue
        for k in range(len(ws)):
            t0 = start if k == 0 else ws[k]["inicio"]
            t1 = ws[k + 1]["inicio"] if k + 1 < len(ws) else end
            t0 = max(t0, events[-1][0] if events and k else t0)
            if t1 - t0 < 0.01:
                continue
            events.append((t0, t1, render(k)))
    return [(s + offset, e + offset, txt) for s, e, txt in events]


def hook_events(g, text, an, x, y, t0, t1, W):
    if g.get("mayusculas"):
        text = text.upper()
    size = float(g["tamano"])
    max_chars = max(8, int((W - 180) / (0.5 * size)))
    raw_lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    lines = []
    for ln in raw_lines:
        words = ln.split()
        for i0, i1 in wrap_lines(words, max_chars, 3):
            lines.append(" ".join(words[i0:i1]))
    if not lines:
        return []
    lines = [ass_escape(ln) for ln in lines]
    pos = "\\" + an + "\\pos(" + f"{x:.0f},{y:.0f}" + ")"
    estilo = g.get("estilo", "editorial")
    if estilo == "editorial":
        top = "{" + pos + "}" + "\\N".join(lines[:-1] + ["{\\i1}" + lines[-1]])
        if len(lines) == 1:
            top = "{" + pos + "\\i1}" + lines[0]
        hidden = "{\\1a&HFF&\\3a&HFF&\\4a&HFF&}" + "\\N".join(lines[:-1]) + "\\N" if len(lines) > 1 else ""
        under = ("{" + pos + "}" + hidden + "{\\1a&H00&\\i1\\u1\\c" + ass_inline(g["acento"]) + "}" + lines[-1])
        return [(t0, t1, under, "HookUnder", 0), (t0, t1, top, "Hook", 1)]
    return [(t0, t1, "{" + pos + "}" + "\\N".join(lines), "Hook", 0)]


def build_ass(path, W, H, cap_sec, cap_events, hook_cfg=None, hook_evs=()):
    styles = []
    if cap_sec:
        styles.append(style_line("Sub", cap_sec["fuente"], cap_sec["tamano"], cap_sec["color"],
                                 cap_sec.get("negrita", True), outline=cap_sec.get("contorno", 0),
                                 shadow=cap_sec.get("sombra", 0)))
    if hook_cfg:
        est = hook_cfg.get("estilo", "editorial")
        size = hook_cfg["tamano"]
        if est == "caja":
            styles.append(style_line("Hook", hook_cfg["fuente"], size, hook_cfg["color"], True,
                                     outline=round(size * 0.22, 1), shadow=0, outline_col=hook_cfg["caja"],
                                     back_col=hook_cfg["caja"], back_alpha=0, border_style=3))
        elif est == "simple":
            styles.append(style_line("Hook", hook_cfg["fuente"], size, hook_cfg["color"], True,
                                     outline=0, shadow=2.5))
        else:
            styles.append(style_line("Hook", hook_cfg["fuente"], size, hook_cfg["color"], False,
                                     outline=0.8, shadow=0, outline_col=hook_cfg["color"]))
            styles.append(style_line("HookUnder", hook_cfg["fuente"], size, hook_cfg["acento"], False))
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
             "ScaledBorderAndShadow: yes", "YCbCr Matrix: None", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
             "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
             "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"] + styles + [
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for s, e, txt, style, layer in hook_evs:
        lines.append(f"Dialogue: {layer},{ass_ts(s)},{ass_ts(e)},{style},,0,0,0,,{txt}")
    for s, e, txt in cap_events:
        lines.append(f"Dialogue: 2,{ass_ts(s)},{ass_ts(e)},Sub,,0,0,0,,{txt}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- render

def snap_tramos(tramos, fps):
    """Ajusta los tramos a la rejilla de fotogramas de la fuente; añade n (fotogramas)."""
    f = fps_value(fps)
    for tr in tramos:
        a = int(round(tr["inicio"] * f))
        b = int(round(tr["fin"] * f))
        if b <= a:
            b = a + 1
        tr["inicio"], tr["fin"], tr["n"] = a / f, b / f, b - a
    return tramos


def color_chain(info):
    """Convierte fuentes HDR o BT.2020 (móviles) a BT.709 SDR. Devuelve filtros con coma final o ''."""
    trc = (info.get("trc") or "").lower()
    prim = (info.get("primarias") or "").lower()
    mat = (info.get("matriz") or "").lower()
    if trc in ("arib-std-b67", "smpte2084"):
        if ff_features(ffmpeg_bin())["zscale"]:
            return (f"zscale=tin={trc}:pin=2020:min=2020_ncl:t=linear:npl=100,format=gbrpf32le,"
                    "zscale=p=709,tonemap=hable:desat=0,zscale=t=709:m=709:r=tv,format=yuv420p,")
        sys.stderr.write("clipkit: aviso: fuente HDR y este ffmpeg no tiene zscale; los colores pueden salir "
                         "apagados (usa un ffmpeg con zimg, por ejemplo ffmpeg-full)\n")
        return "colorspace=all=bt709:iall=bt2020:fast=1,format=yuv420p,"
    if prim == "bt2020" or mat.startswith("bt2020"):
        return "colorspace=all=bt709:iall=bt2020:fast=1,format=yuv420p,"
    return ""


def seg_video(idx, fps, n, cc, tail=""):
    """Cadena de vídeo de un tramo: exactamente n fotogramas desde t=0."""
    return (f"[{idx}:v]setpts=PTS-STARTPTS,{cc}{tail}fps={fps},tpad=stop_mode=clone:stop={n},"
            f"trim=end_frame={n},setpts=PTS-STARTPTS")


def seg_audio(idx, d, has_audio, gain_db=None, fade=True):
    """Cadena de audio de un tramo: exactamente d segundos."""
    if not has_audio:
        return f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.6f}"
    gain = f"volume={float(gain_db)}dB," if gain_db else ""
    s = (f"[{idx}:a]asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,{gain}"
         f"atrim=end={d:.6f},apad=whole_dur={d:.6f}")
    if fade:
        fd = min(0.008, d / 4)
        s += f",afade=t=in:d={fd:.4f},afade=t=out:st={d - fd:.6f}:d={fd:.4f}"
    return s


def seg_input(tr, src, fps):
    extra = 2.0 / fps_value(fps)
    return ["-ss", f"{tr['inicio']:.6f}", "-t", f"{tr['n'] / fps_value(fps) + extra:.6f}", "-i", src]


def completo_geom(info, W, H, m):
    sw, sh = info["ancho"], info["alto"]
    vw = even(W - 2 * m)
    vh = even(vw * sh / sw)
    if vh > H - 2 * m:
        vh = even(H - 2 * m)
        vw = even(vh * sw / sh)
    return vw, vh, (W - vw) // 2, (H - vh) // 2


def clip_layout(enc, info, W, H, cfg, tr, fps, dur, inp, out, n):
    """Filtros que convierten [inp] (fuente) en [out] (lienzo vertical)."""
    sw, sh = info["ancho"], info["alto"]
    f = []
    if enc == "completo":
        vw, vh, x0, y0 = completo_geom(info, W, H, int(cfg.get("margen_video", 44)))
        fondo = cfg.get("fondo", {})
        if fondo.get("tipo") == "desenfoque":
            f.append(f"[{inp}]split[{n}a][{n}b]")
            f.append(f"[{n}a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                     f"boxblur=40:4,eq=brightness=-0.18[{n}bg]")
            f.append(f"[{n}b]scale={vw}:{vh}:flags=lanczos,setsar=1[{n}fg]")
        else:
            col = fondo.get("color", "#000000").lstrip("#")
            f.append(f"color=c=0x{col}:s={W}x{H}:r={fps}:d={dur + 0.5:.3f}[{n}bg]")
            f.append(f"[{inp}]scale={vw}:{vh}:flags=lanczos,setsar=1[{n}fg]")
        f.append(f"[{n}bg][{n}fg]overlay={x0}:{y0}:shortest=1,setsar=1[{out}]")
    elif enc == "recorte":
        cw = min(sw, even(sh * W / H))
        cx = float(tr.get("centro_x", cfg.get("centro_x", 0.5)))
        x = int(min(max(cx * sw - cw / 2, 0), sw - cw))
        f.append(f"[{inp}]crop={cw}:{sh}:{x}:0,scale={W}:{H}:flags=lanczos,setsar=1[{out}]")
    elif enc == "pila":
        zonas = tr.get("zonas") or cfg.get("zonas") or [[0, 0, 0.5, 1], [0.5, 0, 0.5, 1]]
        hh = H // 2
        r = W / hh
        f.append(f"[{inp}]split[{n}z0][{n}z1]")
        for k, (zx, zy, zw, zh) in enumerate(zonas[:2]):
            px, py, pw, ph = zx * sw, zy * sh, zw * sw, zh * sh
            if pw / ph > r:
                cw, ch = even(ph * r), even(ph)
            else:
                cw, ch = even(pw), even(pw / r)
            cx, cy = int(px + (pw - cw) / 2), int(py + (ph - ch) / 2)
            f.append(f"[{n}z{k}]crop={cw}:{ch}:{cx}:{cy},scale={W}:{hh}:flags=lanczos,setsar=1[{n}p{k}]")
        f.append(f"[{n}p0][{n}p1]vstack,setsar=1[{out}]")
    else:  # vertical
        f.append(f"[{inp}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[{out}]")
    return f


def clip_positions(enc, info, W, H, cfg, sub_pos):
    over_hook, over_sub = ("an8", W / 2, H * 0.11), ("an2", W / 2, H * 0.74)
    hook, default_sub = over_hook, over_sub
    bands = False
    if enc == "completo":
        vw, vh, x0, y0 = completo_geom(info, W, H, int(cfg.get("margen_video", 44)))
        if y0 >= H * 0.12:   # hay franjas de verdad: textos fuera del vídeo
            bands = True
            hook = ("an2", W / 2, y0 - H * 0.035)
            default_sub = ("an8", W / 2, y0 + vh + H * 0.03)
    elif enc == "pila":
        default_sub = ("an5", W / 2, H / 2)
    table = {"inferior": over_sub, "centro": ("an5", W / 2, H / 2), "superior": ("an8", W / 2, H * 0.2)}
    sub = default_sub if (sub_pos == "bajo_video" and bands) else table.get(sub_pos, default_sub)
    return hook, sub


def logo_filters(logo, W, H, base, out, idx):
    ancho = int(logo.get("ancho", 120))
    op = float(logo.get("opacidad", 0.9))
    m = 40
    esq = logo.get("esquina", "sup_der")
    x = f"{m}" if "izq" in esq else f"W-w-{m}"
    y = f"{m}" if "sup" in esq else f"H-h-{m}"
    return [f"[{idx}:v]scale={ancho}:-1,format=rgba,colorchannelmixer=aa={op}[lg]",
            f"[{base}][lg]overlay={x}:{y}:shortest=0:eof_action=repeat[{out}]"]


def ass_filter(has_fonts):
    """ffmpeg se ejecuta dentro de la carpeta temporal: rutas relativas sin escapes."""
    return "ass=subs.ass:fontsdir=fonts" if has_fonts else "ass=subs.ass"


def prepare_fonts(prof, tmp):
    src = prof.get("fuentes_dir")
    if not (src and Path(src).is_dir()):
        return False
    dst = tmp / "fonts"
    try:
        os.symlink(src, dst)
    except OSError:
        shutil.copytree(src, dst)
    return True


def script_args(path):
    """-/filter_complex en ffmpeg 7+ y -filter_complex_script en versiones anteriores (se prueba una vez)."""
    if "flag" not in _CACHE:
        tmp = Path(tempfile.mkdtemp(prefix="clipkit_f_"))
        try:
            g = tmp / "g.txt"
            g.write_text("[0:v]null[o]", encoding="utf-8")
            p = run([ffmpeg_bin(), "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "color=s=16x16:d=0.1",
                     "-/filter_complex", str(g), "-map", "[o]", "-f", "null", "-"], check=False)
            _CACHE["flag"] = "-/filter_complex" if p.returncode == 0 else "-filter_complex_script"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return [_CACHE["flag"], str(path)]


def loudnorm_two_pass(src, dst, snd, duration):
    ff = ffmpeg_bin()
    I, TP = float(snd["lufs"]), float(snd["pico"])
    p = run([ff, "-hide_banner", "-nostats", "-i", src, "-vn", "-af",
             f"loudnorm=I={I}:TP={TP}:LRA=11:print_format=json", "-f", "null", "-"], check=False)
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if not m:
        shutil.move(src, dst)
        return None
    d = json.loads(m[-1])
    try:
        lufs = float(d["input_i"])
    except ValueError:
        lufs = float("-inf")
    if not math.isfinite(lufs) or lufs < -70:   # silencio: no normalizar
        shutil.move(src, dst)
        return d
    af = (f"loudnorm=I={I}:TP={TP}:LRA=11:measured_I={d['input_i']}:measured_TP={d['input_tp']}:"
          f"measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:offset={d['target_offset']}:"
          f"linear=true:print_format=summary,aresample=48000,atrim=duration={duration:.9f}")
    run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-map", "0:v", "-map", "0:a",
         "-c:v", "copy", "-af", af, "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", dst])
    os.remove(src)
    return d


def video_codec_args(prof):
    v = prof["video"]
    tags = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    if v.get("codificador") == "h264_videotoolbox":
        return ["-c:v", "h264_videotoolbox", "-b:v", str(v.get("bitrate", "16M")), "-pix_fmt", "yuv420p"] + tags
    return ["-c:v", "libx264", "-preset", str(v.get("preset", "medium")), "-crf", str(v.get("crf", 18)),
            "-pix_fmt", "yuv420p"] + tags


def find_segment(tramos, t_out):
    off = 0.0
    for k, tr in enumerate(tramos):
        d = tr["fin"] - tr["inicio"]
        if t_out < off + d or k == len(tramos) - 1:
            return k, tr["inicio"] + min(max(t_out - off, 0), max(d - 0.001, 0))
        off += d
    return 0, tramos[0]["inicio"]


def load_captions(job, enabled):
    if not enabled:
        return []
    p = job["_dir"] / "subtitulos.json"
    if isinstance(job.get("subtitulos"), str):
        p = resolve(job["_dir"], job["subtitulos"])
    if not p.exists():
        die(f"faltan subtítulos: ejecuta `clipkit.py subtitulos {job['_path']}` o desactívalos en el trabajo")
    return load_json(p)["bloques"]


def require_render():
    ff = ffmpeg_bin()
    feat = ff_features(ff)
    if not feat["libass"]:
        die(f"{ff} no tiene libass (subtítulos). En Mac: `brew install ffmpeg-full` y "
            f"`python3 clipkit.py entorno --guardar`")
    return ff


def out_path(a, job, default_name):
    if a.salida:
        return Path(a.salida).expanduser().resolve()
    if job.get("salida"):
        return Path(job["salida"])
    return job["_dir"] / default_name


def cmd_render(a):
    job = load_job(a.trabajo)
    prof = load_profile(job.get("perfil"))
    require_render()
    if job["tipo"] == "clip":
        render_clip(job, prof, a)
    else:
        render_mid(job, prof, a)


def logo_cfg(cfg, job):
    logo = cfg.get("logo")
    if not (logo and logo.get("archivo")):
        return None
    logo = dict(logo)
    base = Path(job["perfil"]).parent if job.get("perfil") else job["_dir"]
    logo["archivo"] = str(resolve(base, logo["archivo"]).resolve())
    return logo


def render_frame(ff, tmp, inputs, graph, last, out):
    gfile = tmp / "graph.txt"
    gfile.write_text(";\n".join(graph), encoding="utf-8")
    p = run([ff, "-hide_banner", "-loglevel", "verbose", "-y", *inputs, *script_args(gfile), "-map", f"[{last}]",
             "-frames:v", "1", "-update", "1", str(out)], cwd=tmp)
    report_fonts(p.stderr, str(out))


def render_clip(job, prof, a):
    cfg = prof["clips"]
    W, H = cfg["lienzo"]
    info = probe(job["fuente"])
    if "ancho" not in info:
        die("la fuente no tiene vídeo")
    fps = info["fps"]
    f = fps_value(fps)
    cc = color_chain(info)
    jenc = job.get("encuadre") or {}
    enc = jenc.get("tipo") or cfg.get("encuadre", "completo")
    cfg_enc = deep_merge(cfg, jenc)
    tramos = snap_tramos(job["tramos"], fps)
    total = sum(t["n"] for t in tramos) / f
    sec = cfg["subtitulos"]
    sub_on = sec.get("activo", True) and job.get("subtitulos", True) is not False
    blocks = load_captions(job, sub_on)
    hook_pos, sub_pos = clip_positions(enc, info, W, H, cfg_enc, sec.get("posicion", "auto"))
    g = cfg["gancho"]
    gj = job.get("gancho") if isinstance(job.get("gancho"), dict) else {}
    hook_on = g.get("activo", True) and job.get("gancho", True) is not False
    logo = logo_cfg(cfg, job)
    ff = ffmpeg_bin()
    tmp = Path(tempfile.mkdtemp(prefix="clipkit_"))
    try:
        hook_evs = []
        if hook_on:
            t0 = float(gj.get("inicio", 0))
            dur_g = gj.get("duracion", g.get("duracion"))
            t1 = total if dur_g in (None, "todo") else min(total, t0 + float(dur_g))
            hook_evs = hook_events(g, gj.get("texto") or g["texto_defecto"], hook_pos[0], hook_pos[1],
                                   hook_pos[2], t0, t1, W)
        cap_evs = caption_events(blocks, sec, sub_pos[0], sub_pos[1], sub_pos[2]) if sub_on else []
        build_ass(tmp / "subs.ass", W, H, sec if sub_on else None, cap_evs, g if hook_on else None, hook_evs)
        fonts = prepare_fonts(prof, tmp)
        if a.muestra is not None:
            k, src_t = find_segment(tramos, a.muestra)
            inputs = ["-ss", f"{src_t:.3f}", "-i", job["fuente"]]
            graph = [f"[0:v]setpts=PTS-STARTPTS,{cc}fps={fps}[r0]"]
            graph += clip_layout(enc, info, W, H, cfg_enc, tramos[k], fps, 1.0, "r0", "lay", "s0")
            graph.append(f"[lay]setpts=PTS-STARTPTS+{a.muestra:.3f}/TB,{ass_filter(fonts)}[vs]")
            last = "vs"
            if logo:
                inputs += ["-i", logo["archivo"]]
                graph += logo_filters(logo, W, H, last, "vl", 1)
                last = "vl"
            render_frame(ff, tmp, inputs, graph, last, out_path(a, {"_dir": job["_dir"]},
                                                                    f"{job['_path'].stem}_muestra.png"))
            return
        inputs, graph, labels = [], [], ""
        for k, tr in enumerate(tramos):
            n = tr["n"]
            d = n / f
            inputs += seg_input(tr, job["fuente"], fps)
            graph.append(seg_video(k, fps, n, cc) + f"[r{k}]")
            graph += clip_layout(enc, info, W, H, cfg_enc, tr, fps, d, f"r{k}", f"l{k}", f"s{k}")
            graph.append(f"[l{k}]trim=end_frame={n},setpts=PTS-STARTPTS[v{k}]")
            graph.append(seg_audio(k, d, info["audio"], tr.get("ganancia_db")) + f"[a{k}]")
            labels += f"[v{k}][a{k}]"
        graph.append(f"{labels}concat=n={len(tramos)}:v=1:a=1[vc][ac]")
        graph.append(f"[vc]{ass_filter(fonts)}[vs]")
        last = "vs"
        if logo:
            inputs += ["-i", logo["archivo"]]
            graph += logo_filters(logo, W, H, last, "vl", len(tramos))
            last = "vl"
        finish(job, prof, a, inputs, graph, last, "ac", fps, tmp, total)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def norm_v(idx, W, H, fps, n, cc=""):
    tail = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,format=yuv420p,")
    return seg_video(idx, fps, n, cc, tail)


def render_mid(job, prof, a):
    cfg = prof["mids"]
    W, H = cfg["lienzo"]
    info = probe(job["fuente"])
    if "ancho" not in info:
        die("la fuente no tiene vídeo")
    fps = info["fps"]
    f = fps_value(fps)
    cc = color_chain(info)
    tramos = snap_tramos(job["tramos"], fps)
    body = sum(t["n"] for t in tramos) / f
    sec = cfg["subtitulos"]
    sub_on = (sec.get("cuando") != "nunca" or job.get("subtitulos_en")) and job.get("subtitulos", True) is not False
    blocks = load_captions(job, sub_on)
    extras = {}
    for key in ("gancho_video", "cta_video"):
        if job.get(key):
            inf = probe(job[key])
            if "ancho" not in inf:
                die(f"{key} no tiene vídeo")
            inf["n"] = max(1, int(round(inf["duracion"] * f)))
            inf["cc"] = color_chain(inf)
            extras[key] = inf
    pos = sec.get("posicion", "inferior")
    sub_xy = {"inferior": ("an2", W / 2, H * 0.915), "centro": ("an5", W / 2, H / 2),
              "superior": ("an8", W / 2, H * 0.08)}.get(pos, ("an2", W / 2, H * 0.915))
    logo = logo_cfg(cfg, job)
    inserts = job.get("inserciones", []) or []
    ff = ffmpeg_bin()
    tmp = Path(tempfile.mkdtemp(prefix="clipkit_"))
    try:
        cap_evs = caption_events(blocks, sec, *sub_xy) if sub_on else []
        build_ass(tmp / "subs.ass", W, H, sec if sub_on else None, cap_evs)
        fonts = prepare_fonts(prof, tmp)
        if a.muestra is not None:   # segundo del cuerpo del mid, sin el gancho grabado
            k, src_t = find_segment(tramos, a.muestra)
            inputs = ["-ss", f"{src_t:.3f}", "-i", job["fuente"]]
            graph = [norm_v(0, W, H, fps, 1, cc) + "[mv]"]
            last, nin = "mv", 1
            for i, ins in enumerate(inserts):
                if ins["desde"] <= a.muestra <= ins["hasta"]:
                    inputs += ["-i", ins["imagen"]]
                    graph += insert_filters(ins, nin, W, H, last, f"i{i}", single=True)
                    nin += 1
                    last = f"i{i}"
            graph.append(f"[{last}]setpts=PTS-STARTPTS+{a.muestra:.3f}/TB,{ass_filter(fonts)}[vs]")
            last = "vs"
            if logo:
                inputs += ["-i", logo["archivo"]]
                graph += logo_filters(logo, W, H, last, "vl", nin)
                last = "vl"
            render_frame(ff, tmp, inputs, graph, last, out_path(a, {"_dir": job["_dir"]},
                                                                    f"{job['_path'].stem}_muestra.png"))
            return
        inputs, graph, labels = [], [], ""
        for k, tr in enumerate(tramos):
            n = tr["n"]
            d = n / f
            inputs += seg_input(tr, job["fuente"], fps)
            graph.append(norm_v(k, W, H, fps, n, cc) + f"[b{k}v]")
            graph.append(seg_audio(k, d, info["audio"], tr.get("ganancia_db")) + f"[b{k}a]")
            labels += f"[b{k}v][b{k}a]"
        graph.append(f"{labels}concat=n={len(tramos)}:v=1:a=1[bv][ba]")
        last = "bv"
        nin = len(tramos)
        for i, ins in enumerate(inserts):
            inputs += ["-loop", "1", "-framerate", fps, "-t", f"{body + 1:.3f}", "-i", ins["imagen"]]
            graph += insert_filters(ins, nin, W, H, last, f"i{i}")
            nin += 1
            last = f"i{i}"
        graph.append(f"[{last}]{ass_filter(fonts)}[bs]")
        seq = []
        for key, lab in (("gancho_video", "h"), ("cta_video", "c")):
            if key not in extras:
                continue
            inf = extras[key]
            inputs += ["-i", job[key]]
            graph.append(norm_v(nin, W, H, fps, inf["n"], inf["cc"]) + f"[{lab}v]")
            graph.append(seg_audio(nin, inf["n"] / f, inf["audio"], fade=False) + f"[{lab}a]")
            nin += 1
            seq.append((key, f"{lab}v", f"{lab}a"))
        order = [s for s in seq if s[0] == "gancho_video"] + [("cuerpo", "bs", "ba")] + \
                [s for s in seq if s[0] == "cta_video"]
        if len(order) > 1:
            graph.append("".join(f"[{v}][{au}]" for _, v, au in order) + f"concat=n={len(order)}:v=1:a=1[fv][fa]")
            vlast, alast = "fv", "fa"
        else:
            vlast, alast = "bs", "ba"
        if logo:
            inputs += ["-i", logo["archivo"]]
            graph += logo_filters(logo, W, H, vlast, "vl", nin)
            vlast = "vl"
        total = body + sum(inf["n"] for inf in extras.values()) / f
        finish(job, prof, a, inputs, graph, vlast, alast, fps, tmp, total)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def insert_filters(ins, idx, W, H, base, out, single=False):
    modo = ins.get("modo", "completa")
    if modo == "recuadro":
        w = even(W * float(ins.get("ancho", 0.7)))
        sc = f"[{idx}:v]scale={w}:-2,setsar=1[{out}img]"
        pos = "(W-w)/2:(H-h)/2"
    else:
        sc = (f"[{idx}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[{out}img]")
        pos = "0:0"
    if single:
        return [sc, f"[{base}][{out}img]overlay={pos}[{out}]"]
    return [sc, f"[{base}][{out}img]overlay={pos}:enable='between(t,{ins['desde']:.3f},{ins['hasta']:.3f})'"
                f":eof_action=pass[{out}]"]


def report_fonts(stderr, out):
    used = sorted(set(re.findall(r"fontselect: \((.*?)\) -> ([^,\n]*)(?:, -?\d+, ([^\n]*))?", stderr)))
    fuentes = []
    for pedida, ruta, ps in used:
        fam = pedida.split(",")[0].strip()
        usada = Path(ruta).name if "/" in ruta or "\\" in ruta else (ps or ruta)
        key = norm_word(fam.split()[0]) if fam else ""
        fuentes.append({"pedida": pedida, "usada": usada,
                        "coincide": bool(key) and key in norm_word(usada + (ps or ""))})
    res = {"salida": out, "fuentes": fuentes}
    if any(not f["coincide"] for f in fuentes):
        res["aviso"] = ("alguna fuente pedida no parece cargada: revisa el nombre con `clipkit.py fuentes` "
                        "y mira la imagen")
    print(json.dumps(res, ensure_ascii=False, indent=2))


def finish(job, prof, a, inputs, graph, vlabel, alabel, fps, tmp, total):
    ff = ffmpeg_bin()
    gfile = tmp / "graph.txt"
    out = out_path(a, job, f"{job['_path'].stem}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    graph = graph + [f"[{vlabel}]setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[vfin]"]
    gfile.write_text(";\n".join(graph), encoding="utf-8")
    tmp_out = str(tmp / "render.mp4")
    run([ff, "-hide_banner", "-loglevel", "error", "-y", *inputs, *script_args(gfile),
         "-map", "[vfin]", "-map", f"[{alabel}]", "-r", fps, *video_codec_args(prof),
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.9f}",
         "-movflags", "+faststart", tmp_out], cwd=tmp)
    snd = prof.get("sonido")
    measured = None
    if snd:
        measured = loudnorm_two_pass(tmp_out, str(out), snd, total)
    else:
        shutil.move(tmp_out, out)
    info = probe(out)
    lufs = None
    if measured:
        try:
            lufs = float(measured["input_i"])
        except ValueError:
            lufs = None
        if lufs is not None and not math.isfinite(lufs):
            lufs = None
    print(json.dumps({"salida": str(out), "duracion": round(info["duracion"], 3),
                      "duracion_esperada": round(total, 3), "fotogramas_esperados": int(round(total * fps_value(fps))),
                      "ancho": info.get("ancho"), "alto": info.get("alto"), "fps": info.get("fps"),
                      "lufs_antes": lufs}, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- verificar

def cmd_verificar(a):
    ff = ffmpeg_bin()
    info = probe(a.video)
    p = run([ff, "-hide_banner", "-v", "error", "-i", a.video, "-f", "null", "-"], check=False)
    errores = [ln for ln in p.stderr.splitlines() if ln.strip()][:20]
    res = {"video": a.video, **info, "decodifica_entero": p.returncode == 0 and not errores,
           "errores": errores}
    if info.get("audio"):
        q = run([ff, "-hide_banner", "-nostats", "-i", a.video, "-vn", "-af", "ebur128=peak=true",
                 "-f", "null", "-"], check=False)
        tail = q.stderr[q.stderr.rfind("Summary:"):]
        mi = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
        mp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", tail)
        res["lufs"] = float(mi.group(1)) if mi else None
        res["pico_dbtp"] = float(mp.group(1)) if mp and mp.group(1) != "-inf" else None
    if a.esperado is not None:
        res["diferencia_duracion"] = round(info["duracion"] - a.esperado, 3)
    if a.hoja:
        n = 12
        dur = max(info["duracion"], 0.1)
        tw = 270 if info.get("alto", 1) > info.get("ancho", 1) else 480
        run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", a.video, "-vf",
             f"fps={n / dur:.6f},scale={tw}:-2,tile=4x3:padding=4:color=gray", "-frames:v", "1",
             "-update", "1", a.hoja])
        res["hoja"] = a.hoja
    print(json.dumps(res, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- fuentes

def font_names(path):
    """Nombres de la tabla 'name' de un TTF/OTF (o de cada fuente de un TTC)."""
    import struct
    d = Path(path).read_bytes()
    offsets = [0]
    if d[:4] == b"ttcf":
        n = struct.unpack(">I", d[8:12])[0]
        offsets = list(struct.unpack(f">{n}I", d[12:12 + 4 * n]))
    out = []
    for base in offsets:
        num = struct.unpack(">H", d[base + 4:base + 6])[0]
        tables = {}
        for i in range(num):
            tag, _, off, ln = struct.unpack(">4sIII", d[base + 12 + 16 * i:base + 28 + 16 * i])
            tables[tag] = (off, ln)
        names, rank = {}, {}
        if b"name" in tables:
            off = tables[b"name"][0]
            _, cnt, so = struct.unpack(">HHH", d[off:off + 6])
            for j in range(cnt):
                pid, eid, lid, nid, ln, o = struct.unpack(">HHHHHH", d[off + 6 + 12 * j:off + 18 + 12 * j])
                if nid not in (1, 2, 4, 16, 17):
                    continue
                r = 0 if (pid == 3 and lid == 0x409) else 1 if pid == 3 else 2 if pid == 0 else 3
                if r >= rank.get(nid, 9):
                    continue
                raw = d[off + so + o:off + so + o + ln]
                try:
                    names[nid] = raw.decode("utf-16-be") if pid in (0, 3) else raw.decode("latin-1")
                    rank[nid] = r
                except UnicodeDecodeError:
                    pass
        out.append({"familia": names.get(1), "estilo": names.get(2), "nombre_completo": names.get(4),
                    "familia_tipografica": names.get(16), "variable": b"fvar" in tables})
    return out


def cmd_fuentes(a):
    res = []
    for f in sorted(Path(os.path.expanduser(a.carpeta)).glob("*")):
        if f.suffix.lower() in (".ttf", ".otf", ".ttc"):
            try:
                for n in font_names(f):
                    res.append({"archivo": f.name, **n})
            except Exception as e:  # archivo dañado o formato raro
                res.append({"archivo": f.name, "error": str(e)})
    print(json.dumps(res, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- fotograma

def cmd_fotograma(a):
    run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{a.t:.3f}", "-i", a.video,
         "-frames:v", "1", "-update", "1", a.salida])
    print(json.dumps({"salida": a.salida, "t": a.t}, ensure_ascii=False))


# ---------------------------------------------------------------- muestra de estilo

def cmd_muestra(a):
    tmp = Path(tempfile.mkdtemp(prefix="clipkit_m_"))
    try:
        info = probe(a.video)
        dur = info["duracion"]
        t = a.t if a.t is not None else min(dur / 2, 30.0)
        t = max(0.0, min(t, dur - 1.0))
        job = {"tipo": a.formato, "perfil": str(Path(a.perfil).resolve()), "fuente": str(Path(a.video).resolve()),
               "tramos": [[t, min(t + 5, dur)]]}
        if a.formato == "clip" and a.gancho:
            job["gancho"] = {"texto": a.gancho.replace("\\n", "\n")}
        if a.formato == "mid" and load_profile(a.perfil)["mids"]["subtitulos"].get("cuando") != "nunca":
            job["subtitulos_en"] = [[0, 1e9]]
        save_json(tmp / "trabajo.json", job)
        n = len(SAMPLE_WORDS)
        words = [{"texto": w, "inicio": round(i * 0.3, 2), "fin": round(i * 0.3 + 0.25, 2),
                  "enfasis": w == "destacada"} for i, w in enumerate(SAMPLE_WORDS)]
        prof = load_profile(a.perfil)
        sec = prof["clips" if a.formato == "clip" else "mids"]["subtitulos"]
        blocks = make_blocks(words, int(sec["max_caracteres"]), int(sec["max_lineas"]))
        save_json(tmp / "subtitulos.json", {"bloques": [{"palabras": b} for b in blocks]})
        last_block_end = blocks[-1][-1]["fin"] if blocks else 0
        ns = argparse.Namespace(trabajo=str(tmp / "trabajo.json"), muestra=min(last_block_end, n * 0.3),
                                salida=str(Path(a.salida).resolve()))
        cmd_render(ns)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(prog="clipkit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="orden", required=True)

    s = sub.add_parser("entorno", help="comprueba herramientas")
    s.add_argument("--python", action="append", help="otro Python donde buscar motores (repetible)")
    s.add_argument("--guardar", action="store_true", help="guarda el ffmpeg válido en config.json")
    s.set_defaults(fn=cmd_entorno)

    s = sub.add_parser("transcribir", help="audio -> palabras con tiempos")
    s.add_argument("medio")
    s.add_argument("salida")
    s.add_argument("--motor", default="auto", choices=["auto", "mlx_whisper", "faster_whisper", "whisper"])
    s.add_argument("--modelo")
    s.add_argument("--idioma", help="código ISO, p. ej. es")
    s.add_argument("--python", help="Python donde está instalado el motor")
    s.add_argument("--desde", type=float)
    s.add_argument("--hasta", type=float)
    s.set_defaults(fn=cmd_transcribir)

    s = sub.add_parser("_motor")
    s.add_argument("wav")
    s.add_argument("salida")
    s.add_argument("--motor", required=True)
    s.add_argument("--modelo")
    s.add_argument("--idioma")
    s.set_defaults(fn=cmd_motor)

    s = sub.add_parser("leer", help="transcripción legible o búsqueda de frase")
    s.add_argument("palabras")
    s.add_argument("--desde", type=float)
    s.add_argument("--hasta", type=float)
    s.add_argument("--pausa", type=float, default=0.7, help="pausa que abre línea nueva (s)")
    s.add_argument("--buscar", help="frase exacta; devuelve tiempos y puntos de corte")
    s.set_defaults(fn=cmd_leer)

    s = sub.add_parser("bordes", help="energía de la voz alrededor de puntos de corte")
    s.add_argument("medio")
    s.add_argument("tiempos", type=float, nargs="+")
    s.add_argument("--ventana", type=float, default=0.25)
    s.add_argument("--umbral", type=float, default=-45.0, help="dB por debajo de los cuales hay silencio")
    s.set_defaults(fn=cmd_bordes)

    s = sub.add_parser("subtitulos", help="genera subtitulos.json editable")
    s.add_argument("trabajo")
    s.add_argument("--salida")
    s.add_argument("--forzar", action="store_true")
    s.set_defaults(fn=cmd_subtitulos)

    s = sub.add_parser("render", help="renderiza un trabajo")
    s.add_argument("trabajo")
    s.add_argument("--muestra", type=float,
                   help="solo un PNG en este segundo del montaje (en mids, del cuerpo, sin el gancho grabado)")
    s.add_argument("--salida")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("verificar", help="comprueba un vídeo exportado")
    s.add_argument("video")
    s.add_argument("--esperado", type=float, help="duración esperada (s)")
    s.add_argument("--hoja", help="PNG con 12 fotogramas repartidos")
    s.set_defaults(fn=cmd_verificar)

    s = sub.add_parser("fuentes", help="nombres de familia de las fuentes de una carpeta")
    s.add_argument("carpeta")
    s.set_defaults(fn=cmd_fuentes)

    s = sub.add_parser("fotograma", help="extrae un fotograma de la fuente (para encuadrar)")
    s.add_argument("video")
    s.add_argument("t", type=float)
    s.add_argument("salida")
    s.set_defaults(fn=cmd_fotograma)

    s = sub.add_parser("muestra", help="fotograma de prueba del estilo de un perfil")
    s.add_argument("perfil")
    s.add_argument("video")
    s.add_argument("salida")
    s.add_argument("--formato", choices=["clip", "mid"], default="clip")
    s.add_argument("--t", type=float, help="segundo de la fuente")
    s.add_argument("--gancho", help="texto del gancho de prueba (\\n para saltos)")
    s.set_defaults(fn=cmd_muestra)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
~~~~~

### `~/ClipsYMids/CONFIGURAR.md`

~~~~~markdown
# Configurar un canal

Lo usan las skills `clips-verticales` y `mids-desde-grabaciones`. Ejecútalo cuando:

- no exista ningún perfil en `~/ClipsYMids/canales/*/perfil.json`;
- el usuario pida configurar otro canal o negocio;
- el usuario pida cambiar el estilo (repite solo la parte afectada).

Cada canal tiene su carpeta: `~/ClipsYMids/canales/<slug>/` con `perfil.json`, `recursos/` (fuentes, logo, vídeos de CTA) y `trabajos/`. Así una misma persona o agencia puede llevar varios canales sin mezclar estilos.

## Cómo preguntar

- Pregunta por rondas de hasta 3 preguntas, sin jerga. Usa la herramienta de preguntas de tu entorno si existe; si no, pregunta en el chat con las opciones numeradas. Divide las rondas siguientes si incluyen más decisiones.
- Pon primero la opción recomendada y acepta «lo que recomiendes» como respuesta válida.
- Antes de preguntar, mira lo que ya puedes saber. Si el usuario te da un vídeo suyo, ábrelo con `clipkit.py fotograma` y míralo: el encuadre y la gente que sale responden parte de las preguntas.
- No preguntes lo que no vaya a usar. Si solo quiere clips, sáltate la ronda de mids, y al revés.
- Al comenzar, explica en una frase la diferencia entre clips y mids y pregunta qué quiere producir: ambos (recomendado para reaprovechar grabaciones), solo clips o solo mids. Guarda la elección en `formatos`. Tras cada ronda, guarda el perfil parcial y sus pendientes: al retomar, completa únicamente lo que falte.
- Si pide ayuda con guiones, explica la diferencia: aquí los guiones son las instrucciones de trabajo de la IA y los textos del gancho/CTA. Puede ayudarte a redactar un gancho o intro para grabar; no promete ideación automática ni inventa una intervención que no existe en la fuente.

## Ronda 1 · Canal y audiencia (siempre)

1. Nombre del canal o negocio y de qué trata, en una frase.
2. Idioma de los vídeos.
3. Su espectador o cliente ideal: en qué situación está, qué quiere conseguir y qué se lo impide. Con esto se eligen los momentos que valen la pena.
4. Quién habla en las grabaciones: nombres y papel (presentador, invitado, cliente, alumno…).

## Ronda 2 · Clips verticales: encuadre y textos

1. Plataformas de destino: Reels, TikTok o Shorts. Las tres usan 1080×1920 y una interfaz parecida, y la herramienta deja libres sus zonas tapadas.
2. Encuadre, si graba en horizontal:
   - **Vídeo completo centrado** (recomendado): el plano horizontal entero en el centro, sin recortar, con franjas arriba y abajo para el gancho y los subtítulos. El fondo de las franjas puede ser negro, un color de marca o el propio vídeo desenfocado.
   - **Recorte vertical**: el plano se recorta a 9:16 sobre la persona. Se ve más grande, pero se pierde lo que haya a los lados.
   - **Dos personas apiladas**: cada una en una mitad (para podcasts o entrevistas a dos cámaras o en plano compartido).
   - **La fuente ya es vertical**.
3. Gancho escrito arriba:
   - **Editorial** (recomendado): texto blanco limpio con la última línea en cursiva y subrayada con el color de acento.
   - **Caja tipo rótulo**: cada línea sobre una caja de color, como el texto nativo de Instagram o TikTok.
   - **Simple**: texto en negrita con sombra.
   - Sin gancho.
   Pregunta también si dura todo el clip o solo los primeros segundos.
4. Subtítulos:
   - **Palabra a palabra** (recomendado): las palabras aparecen al decirse, sin que el bloque baile.
   - **Palabra activa resaltada**: la frase entera visible y la palabra que se está diciendo en color.
   - **Frase completa**.
   - Sin subtítulos.
   Pregunta además el color de las palabras destacadas y si van en mayúsculas.

## Ronda 3 · Marca

1. Tipografía: el nombre de una fuente instalada o sus archivos `.ttf`/`.otf`, que se copian a `recursos/fuentes/`. Sin fuente propia: Helvetica Neue en Mac.
   - Pide los archivos estáticos (Regular, Bold, Italic…), no la versión variable: con una fuente variable solo se carga su grosor por defecto. En Google Fonts están en la carpeta `static` de la descarga.
   - El nombre que va en el perfil es la `familia` exacta que devuelve `clipkit.py fuentes ~/ClipsYMids/canales/<slug>/recursos/fuentes`. A veces incluye el grosor («Montserrat ExtraBold»); en ese caso pon `"negrita": false`.
2. Colores de marca en hex. El acento se usa para el subrayado del gancho y las palabras destacadas.
3. Logo o marca de agua: un PNG con fondo transparente y la esquina donde va, o ninguno.
4. Referencia: si tiene una captura de un reel cuyo estilo le guste, pídesela, mírala y propón los valores que la reproducen (encuadre, colores, tipografía parecida, posición de los textos).

## Ronda 4 · Mids (solo si va a hacer mids)

1. Qué graba: consultorías, llamadas con clientes, podcasts o entrevistas, directos, clases o webinars.
2. Permiso: ¿los participantes han aceptado que se publique? ¿Hay algo que se deba ocultar o cortar, como apellidos, empresas, cifras privadas o pantallas con datos? Sin permiso claro, los mids se preparan, pero quedan marcados como «permiso pendiente» en su ficha.
3. Subtítulos en mids:
   - **Solo cuando habla el invitado o cliente** (recomendado si su audio llega peor, por ejemplo por Zoom).
   - Siempre.
   - Nunca.
4. Cierre: ¿qué recurso o siguiente paso ofrece, con qué promesa y en qué enlace? ¿Tiene un vídeo de llamada a la acción grabado para pegar al final, o ganchos grabados aparte? Si falta, el CTA queda pendiente en la ficha; no se inventa.

## Ronda 5 · Entrega

1. Dónde dejar los vídeos terminados: una carpeta local (por defecto `~/ClipsYMids/canales/<slug>/exportados/`) o Google Drive, si tu entorno tiene conector o acceso a su API. Para Drive, la carpeta padre.
2. Si quiere repartir clips por días: cuántos por día. Se crean carpetas `AAAA-MM-DD · día de la semana/`.
3. Si quiere que, después de subir a Drive y comprobar la copia, los MP4 locales vayan a la Papelera (siempre recuperables).

El motor de transcripción y la sonoridad no se preguntan: se usa el motor comprobado en la instalación y -14 LUFS con pico de -1 dBTP como punto de partida. Cámbialos si el usuario o el destino necesitan otro nivel.

Tras configurar el canal, ofrece el editor siguiendo `~/ClipsYMids/STUDIO.md`. Si ya eligió, reutiliza esa respuesta. No instalarlo no impide hacer clips ni mids.

## Guardar el perfil

Escribe `~/ClipsYMids/canales/<slug>/perfil.json`. Solo hace falta lo que difiera de los valores por defecto de `clipkit.py`, pero guarda siempre `canal` y `entrega`. Las claves que no reconozca la herramienta las leen las skills.

```json
{
  "formatos": ["clips", "mids"],
  "editor": {"modo": "clipkit", "ruta": null},
  "canal": {
    "nombre": "Nombre del canal",
    "slug": "nombre-del-canal",
    "descripcion": "De qué trata, en una frase",
    "idioma": "es",
    "audiencia": {"situacion": "...", "objetivo": "...", "obstaculo": "..."},
    "hablantes": [{"nombre": "Ana", "papel": "presentadora"}, {"nombre": "clientes", "papel": "invitado"}]
  },
  "fuentes_dir": "recursos/fuentes",
  "clips": {
    "lienzo": [1080, 1920],
    "encuadre": "completo",
    "margen_video": 44,
    "fondo": {"tipo": "color", "color": "#000000"},
    "gancho": {"activo": true, "estilo": "editorial", "texto_defecto": "Escribe aquí\ntu gancho",
               "fuente": "Helvetica Neue", "tamano": 70, "color": "#FFFFFF", "acento": "#B28CFF",
               "caja": "#000000", "mayusculas": false, "duracion": null},
    "subtitulos": {"activo": true, "modo": "palabra", "fuente": "Helvetica Neue", "tamano": 62,
                   "negrita": true, "color": "#FFFFFF", "enfasis": "#B28CFF", "mayusculas": false,
                   "posicion": "auto", "max_lineas": 2, "max_caracteres": 24, "contorno": 0, "sombra": 2},
    "logo": null
  },
  "mids": {
    "lienzo": [1920, 1080],
    "tipos_grabacion": ["consultorías"],
    "duracion_referencia": [5, 15],
    "subtitulos": {"cuando": "invitado", "modo": "frase", "tamano": 64, "max_lineas": 1, "max_caracteres": 44,
                   "contorno": 2},
    "cta": {"recurso": null, "promesa": null, "enlace": null, "video": null},
    "privacidad": {"consentimiento": "pendiente", "ocultar": []},
    "logo": null
  },
  "sonido": {"lufs": -14, "pico": -1},
  "entrega": {
    "destino": "local",
    "carpeta": "~/ClipsYMids/canales/nombre-del-canal/exportados",
    "drive_carpeta": null,
    "por_dia": null,
    "zona_horaria": "Europe/Madrid",
    "limpiar_tras_subir": false
  },
  "transcripcion": {"motor": "mlx_whisper", "python": "/ruta/al/python", "modelo": null}
}
```

Valores admitidos:

- `clips.encuadre`: `completo`, `recorte`, `pila`, `vertical`. Con `recorte`, `centro_x` (de 0 a 1) fija dónde está la persona; con `pila`, `zonas` da los dos recuadros como `[x, y, ancho, alto]` en fracciones de la fuente.
- `fondo.tipo`: `color` o `desenfoque`.
- `gancho.estilo`: `editorial`, `caja`, `simple`. `gancho.duracion`: `null` (todo el clip) o segundos.
- `subtitulos.modo`: `palabra`, `resaltado`, `frase`. `subtitulos.posicion`: `auto`, `bajo_video`, `inferior`, `centro`, `superior`.
- `mids.subtitulos.cuando`: `nunca`, `invitado`, `siempre`.
- `logo`: `{"archivo": "recursos/logo.png", "esquina": "sup_der", "ancho": 120, "opacidad": 0.9}`, con esquina `sup_izq`, `sup_der`, `inf_izq` o `inf_der`.
- `video` (opcional): `{"codificador": "libx264", "crf": 18, "preset": "medium"}`. En Mac también vale `h264_videotoolbox` con `"bitrate": "16M"`, más rápido y con algo menos de calidad por bit.

Si los textos se ven demasiado grandes o pequeños, cambia `tamano` y, en los subtítulos, `max_caracteres` en proporción (más tamaño, menos caracteres por línea).

## Muestra y aprobación

1. Pide un vídeo real del canal (o usa el que ya te haya dado). Comprueba su duración: los segundos siguientes son ejemplos; elige un punto que exista y tenga voz. Si no hay vídeo, guarda el perfil como pendiente de muestra y no marques `aprobado`.
2. Genera la muestra de cada formato elegido. Omite la de clips cuando solo quiera mids:

   ```bash
   python3 ~/ClipsYMids/clipkit.py muestra ~/ClipsYMids/canales/<slug>/perfil.json VIDEO.mp4 muestra-clip.png --t 60 --gancho "Así se verá\ntu gancho"
   python3 ~/ClipsYMids/clipkit.py muestra ~/ClipsYMids/canales/<slug>/perfil.json VIDEO.mp4 muestra-mid.png --formato mid --t 60
   ```

3. Mira tú la imagen antes de enseñarla. La orden informa de qué fuente se pidió y cuál se usó; si devuelve un `aviso`, revisa el nombre de la familia. Comprueba también que nada tapa la cara, que se lee a tamaño de móvil y que el color de acento contrasta con el fondo.
4. Enséñasela al usuario y ajusta hasta que diga que sí. Guarda en el perfil `"aprobado": "AAAA-MM-DD"`.
5. Termina con dos líneas: cómo pedir clips («haz clips de este vídeo» o «clip del 12:30 al 14:05») y cómo pedir mids («saca mids de esta grabación»).
~~~~~

### `~/ClipsYMids/CORTES.md`

~~~~~markdown
# Cortes precisos

Método común de `clips-verticales` y `mids-desde-grabaciones`. El principio: la edición existe para que el espectador entienda mejor lo que se cuenta. Lo que no ayuda a entender, o a sostener la atención para entender, sobra.

## 1. Leer antes de cortar

- Transcribe la fuente entera una vez y guarda el JSON junto al trabajo:
  `python3 ~/ClipsYMids/clipkit.py transcribir FUENTE.mp4 FUENTE.palabras.json --idioma es` (añade `--motor`, `--python` y `--modelo` según `transcripcion` del perfil).
- Lee el tramo completo con margen antes de decidir: `clipkit.py leer FUENTE.palabras.json --desde 700 --hasta 900`.
- Para localizar una frase y su punto de corte: `clipkit.py leer FUENTE.palabras.json --buscar "el mayor error"`. Devuelve `corte_antes` y `corte_despues` en el punto medio entre palabras. Son un punto de partida, no el corte final.

## 2. Qué quitar y qué conservar

- Quita muletillas, falsos arranques, retomas, repeticiones accidentales, instrucciones al editor, esperas y desvíos que no aportan.
- Conserva afirmaciones, negaciones, condiciones, pruebas y matices. Una repetición retórica se queda solo si su énfasis aporta algo que se perdería.
- Nunca recombines frases para atribuir a alguien algo que no dijo. Mantén el orden de lo dicho.
- Al quitar un arranque abandonado, comprueba que no te llevas el verbo que introduce lo siguiente («les dices…»). Relee siempre el montaje como frase, no solo como audio limpio.

## 3. Afinar cada borde con el audio

Los tiempos del reconocimiento de voz se desplazan hasta 0,3 s y suelen colocar mal números y finales cortos. Cada borde se decide con la señal:

```bash
python3 ~/ClipsYMids/clipkit.py bordes FUENTE.mp4 734.20 741.85 --ventana 0.25
```

Para cada tiempo devuelve la energía en ese punto, el mínimo cercano y el silencio más próximo (por debajo de -45 dB), además de un perfil cada 10 ms.

- Corta en el silencio más cercano del lado correcto de la palabra. Si en el punto hay voz (más de unos -40 dB), estás cortando una palabra o su cola.
- Deja unos 0,08–0,12 s de aire antes de la primera palabra de cada tramo y 0,10–0,15 s después de la última. Así el empalme respira sin huecos raros.
- Dentro de un clip, acorta a unos 0,25–0,35 s las pausas de más de 0,5 s que no tengan intención. En un mid, deja respirar más: no hay que eliminar cada pausa.
- Si no hay silencio (habla encadenada), corta en el mínimo de energía entre palabras y compruébalo con la transcripción aislada del paso 4.
- Si alguien habla por altavoz o Zoom, sus colas nunca bajan a silencio total: busca el mínimo relativo, no los -45 dB.
- clipkit añade un fundido de audio de 8 ms en cada empalme para evitar chasquidos. No hace falta más.

## 4. Retomas escondidas y titubeos

- El reconocimiento de la grabación entera puede ocultar retomas: una palabra con una duración anormalmente larga, o una frase que suena repetida, es señal de ello.
- Transcribe aislado el fragmento dudoso para verlo: `clipkit.py transcribir FUENTE.mp4 dudoso.json --desde 734.0 --hasta 742.0`, y lee el resultado.
- Antes de quitar un supuesto «eh», transcribe aislado solo ese trozo. Un titubeo suele dar vacío o una alucinación tipo «Gracias»; una palabra real da la palabra. Si es una palabra alargada («aaasegurar»), no la partas.
- Tras quitar trozos pequeños, revisa que no queden tramos de menos de 0,3 s ni pausas de más de 0,55 s sin motivo.

## 5. Verificar el montaje

1. Renderiza y transcribe el resultado: `clipkit.py transcribir SALIDA.mp4 salida.json` y `clipkit.py leer salida.json`.
2. Lee todo el texto: cada unión debe ser gramatical, sin palabras cortadas, restos de la frase quitada ni fragmentos duplicados.
3. Contrasta cada unión dudosa desde los dos lados (transcripción aislada de 2–3 s antes y después del empalme).
4. Si puedes escuchar, escucha las uniones. Si no puedes, dilo claramente al entregar: las medidas y la transcripción no equivalen a una escucha.

## 6. Subtítulos literales

- El texto de los subtítulos es literal: lo que se dijo, aunque suene raro. Corrige los errores del reconocimiento contrastando con el audio, nunca normalizando.
- Para una palabra dudosa, compara tres lecturas: la transcripción de la fuente, la transcripción aislada de su frase y la del montaje. Si ninguna la resuelve, no la inventes: corta la frase si sobra o deja ese tramo sin subtítulo.
- Destaca las palabras por su significado (la idea clave, el número, el contraste): una por bloque, rara vez dos. Ni todas ni al azar.
~~~~~

### `~/ClipsYMids/STUDIO.md`

~~~~~markdown
# Studio Local · editor opcional de la máquina

## Explicarlo antes de preguntar

Sin Studio, la IA edita un `trabajo.json` y los subtítulos, y genera el MP4. Con Studio tienes además una app en el Mac para ver el montaje por pistas, retocar y dejar comentarios sobre un fotograma; la IA opera ese mismo proyecto. Las fuentes originales se conservan en ambos casos.

Explica brevemente las funciones disponibles:

- Biblioteca con proyectos y carpetas; reproducción y cortes al fotograma.
- Encuadre, zoom, color SDR, imágenes, vídeos superpuestos, títulos y subtítulos.
- Voz, música y efectos por pistas, volúmenes y fundidos.
- ⌘F para dejar texto y dibujo en el fotograma; «aplica mis comentarios» para encargar cambios a la IA.
- Exportación H.264 en `~/Movies/Studio Local`, y CLI/MCP para que el agente edite por código.
- Interfaz opcional para iPhone, que requiere una configuración aparte; no se instala por defecto.

Studio no selecciona momentos ni transcribe solo: lo hacen la IA y clipkit. No incluye generación 3D ni publicación automática. El estilo preciso debe comprobarse en sus fotogramas; clipkit y Studio usan pintores distintos y no producen necesariamente imágenes idénticas.

Pregunta: **«¿Quieres trabajar con Studio Local, el editor visual para revisar los vídeos y dejar comentarios?»** Ofrece instalarlo ahora (recomendado en Apple Silicon), usar el que ya tiene o seguir sin él. Guarda su elección. Si cambia de idea más tarde, retoma aquí.

## Instalar o reutilizar

Fuente pública: [Alex-human/studio-local](https://github.com/Alex-human/studio-local). Solo Mac Apple Silicon; este paquete acompaña la actualización 1.14.4 del 14-10-2026 y las nuevas descargas usan la rama `main`. Comprueba los requisitos del repositorio que vayas a instalar. No copies el editor privado de quien distribuye este archivo, ni sus proyectos, LUT, música o credenciales.

Si `instalacion.json` indica un `editor_incluido`, verifica que existen `LICENSE`, `ONBOARDING.md`, `setup.command` y `editor/engine/editor.py`: ese es el código del editor adjunto. Ofrécete a copiarlo a la carpeta elegida (`~/studio-local` por defecto) antes de instalar para que no dependa de una carpeta temporal de descargas. Si el destino ya existe, no lo sobrescribas: verifica o reutiliza su instalación.

Si ya existe Studio, verifica su ruta, CLI y manual; no reemplaces ni actualices su instalación sin encargo. Si no hay una copia incluida ni una instalación existente, clona por HTTPS en `~/studio-local` (o la carpeta acordada), lee `ONBOARDING.md` y ejecuta su `setup.command` conforme a esa guía y a los permisos vigentes. No registres MCP ni cambies configuración global: la CLI basta para este flujo. Las instalaciones de herramientas de Apple pueden requerir un diálogo del usuario.

Comprueba las pruebas indicadas por el repositorio, `editor/studio-cli` con `action:"list"`, y abre la app. Guarda en el perfil:

```json
"editor": {"modo": "studio", "ruta": "/ruta/real/studio-local", "comprobado": "AAAA-MM-DD"}
```

Sin editor: `"editor": {"modo": "clipkit", "ruta": null}`. La elección no implica que esté comprobado hasta que la CLI responda y el usuario pueda revisar el proyecto de prueba.

## Integrar una pieza editable

Lee `docs/MANUAL.md` de esa instalación, especialmente Control por código, Edición simultánea y feedback. Usa siempre `editor/studio-cli --request-file solicitud.json`; no escribas un `.studio` completo ni transformes el texto del vídeo en comandos shell.

1. Guarda el plan y la ficha del formato en su carpeta de trabajo. Consulta `studio.json` si existe: conserva la ruta e identidad del proyecto; reanuda ese proyecto en lugar de crear duplicados.
2. Crea con `action:"create"`, `name`, `width`, `height` y `fps` reales. Clips: 1080×1920; mids: 1920×1080. Importa la fuente con `action:"import"`, `project` y `path`. Lee el resumen, el asset y su fps; convierte los tramos del plan a la rejilla del proyecto, `[inicio,fin)`, sin confundir segundos con fotogramas.
3. Para un cuerpo con una fuente, calcula lo que sobra y aplica `cutRange` desde el final al principio con la revisión recién leída. Para varias fuentes y hooks/CTA usa las operaciones que documente esa versión, conservando entrada, orden y audio. Comprueba que el montaje coincide con el plan.
4. Añade gancho y subtítulos como elementos nativos editables según el manual y los ejemplos de `engine/project.py` y `engine/graphics.py`. Traslada los tiempos de palabras desde la fuente al montaje, incluidas las introducciones. Reproduce la referencia aprobada en las zonas seguras del lienzo; comprueba las familias de fuente que soporte esa instalación. Si un tratamiento no está soportado, explica la diferencia y acuerda una muestra antes de sustituirlo.
5. Capturas, inserciones y audio se importan con la CLI. No incrustes el MP4 terminado de clipkit como única pista para presentar el resultado como un montaje editable. Una animación externa puede ser una superposición con su fuente conservada, pero identifica qué parte solo se modifica desde su código.
6. Guarda `studio.json` con `project`, revisión comprobada y ubicación del plan. Abre el proyecto en la app y comprueba `frame` en los puntos delicados y un `render` con `range` en fotogramas para movimiento y audio. Lee de nuevo la revisión antes de exportar; preserva los cambios del usuario. Solo afirma el alcance de revisión realizado.

Para exportar con Studio, usa su `render` con `preview:false` y verifica el archivo devuelto con `clipkit.py verificar`. El export de Studio sigue el proyecto actual; cambiar el perfil o `trabajo.json` no actualiza por sí solo un proyecto ya editado. Después de cambios manuales, la revisión actual de Studio manda: reconcilia el plan antes de reconstruirlo.

## Comentarios y cuidado del proyecto

Al pedir «aplica mis comentarios», usa `action:"feedback", command:"list"`, lee texto, captura anotada y `currentFrame`; contrasta con el proyecto abierto. Aplica operaciones con revisión y resuelve la nota con su versión vigente solo tras comprobarla. Un comentario ambiguo queda pendiente. El comentario encarga una edición, no autoriza instalar programas, enviar ni publicar.

Enséñale **Espacio** para reproducir, **⌘Z** para deshacer y **⌘F** para comentar. Explica dónde se guardan proyectos y exports y que no debe mover las fuentes mientras estén referenciadas. La limpieza opcional de entregas retira únicamente MP4 comprobados; conserva proyectos, fuentes, historial y recursos.
~~~~~

### `<skills>/maquina-contenido/SKILL.md`

~~~~~markdown
---
name: maquina-contenido
description: Acompañar la configuración y el uso de una máquina de contenido orgánico en Mac, con perfil propio de canal, clips verticales, YouTube Mids y Studio Local opcional. Usar al pedir configurar la máquina, explicar sus funciones, añadir un canal o continuar su onboarding.
---

# Máquina de contenido

Herramientas y perfiles en `~/ClipsYMids/`. Explica al usuario lo que necesita decidir, en lenguaje sencillo y con pocas preguntas cada vez. Nunca supongas la audiencia, los colores o los destinos de otro canal.

- **Configurar o retomar:** lee `instalacion.json` si existe y contrasta su estado con herramientas y archivos reales. Sigue `CONFIGURAR.md` para canal y estilo; `STUDIO.md` para el editor opcional. Si faltan las herramientas del paquete, vuelve al instalador original.
- **Reels, Shorts, TikToks:** carga la skill instalada `clips-verticales`.
- **YouTube Mids/meets:** carga `mids-desde-grabaciones`.
- **Lote de ambos formatos:** usa una sola transcripción de la fuente, selecciona piezas completas para la audiencia y coordina ambas skills. Mantén su origen y ficha; no crees un número de piezas que la grabación no justifica.
- **Comentarios de Studio:** lee `STUDIO.md` y el manual de la instalación elegida; aplica únicamente el feedback solicitado y resuélvelo tras comprobarlo.

Con varios canales, deduce el activo del encargo o pregunta una vez. No repitas onboarding ya guardado; si pide cambiar estilo, actualiza solo esa parte. Una muestra aprobada fija el estilo; una instalación sin vídeo queda pendiente de prueba.

La máquina selecciona, edita, revisa y entrega. Publicar en redes, conectar cuentas o borrar material requiere el encargo correspondiente; no crea tareas ni bucles en segundo plano. Solo promete capacidades comprobadas en la instalación actual.
~~~~~

### `<skills>/clips-verticales/SKILL.md`

~~~~~markdown
---
name: clips-verticales
description: Crear clips verticales (Reels, TikTok, Shorts) de cualquier canal o negocio a partir de vídeos largos o grabaciones, con cortes precisos, encuadre 9:16, gancho escrito y subtítulos en el estilo configurado del canal, y entregarlos en una carpeta o en Drive repartidos por días. Usar cuando pidan «haz clips», «saca reels, shorts o tiktoks de este vídeo», «clip del minuto X al Y», «propón clips» o «exporta y sube los clips». La primera vez configura el canal con preguntas.
---

# Clips verticales

Convierte momentos de un vídeo largo en clips verticales que se entienden solos desde el primer segundo. El estilo de cada canal vive en su perfil. Las herramientas están en `~/ClipsYMids/`:

- `clipkit.py`: transcripción, bordes de corte, subtítulos, render y verificación;
- `CONFIGURAR.md`: preguntas iniciales y formato del perfil;
- `CORTES.md`: método de corte y de subtítulos literales.
- `STUDIO.md`: editor visual opcional y proyectos nativos editables.

Si falta `~/ClipsYMids/clipkit.py`, pide al usuario que vuelva a ejecutar el instalador.

## 1. Canal y perfil

- Busca perfiles en `~/ClipsYMids/canales/*/perfil.json`.
- Sin ninguno, o si el usuario pide configurar otro canal o cambiar el estilo, sigue `~/ClipsYMids/CONFIGURAR.md` antes de seguir.
- Con varios, deduce el canal por el contexto (nombre, carpeta del vídeo) o pregunta.
- Lee el perfil entero: audiencia, hablantes, estilo, entrega y motor de transcripción.
- Con `editor.modo: "studio"`, lee `STUDIO.md` y usa la instalación guardada. El plan siguiente sigue siendo la ficha de trabajo; el montaje editable y su exportación se realizan en Studio, conservando los cambios manuales. No instales el editor si no lo eligió.

## 2. Qué clips hacer

**Si el usuario marca los tramos** («clip 1 del 12:30 al 14:05», notas con «inicio clip 2 / final clip 2», o un archivo con la lista):

- Empareja inicios y finales por número, no por orden de aparición. Acepta números escritos o en cifras.
- Un inicio o final ausente, duplicado o invertido deja ese clip pendiente: no lo adivines ni bloquees los demás. Informa al terminar.
- Varios tramos para un mismo número forman un único clip, en ese orden.
- No crees clips fuera de lo marcado, pero puedes proponer momentos buenos que hayas visto.

**Si pide que propongas** («saca clips», «propón clips»):

- Transcribe y lee la grabación entera (`CORTES.md`, paso 1).
- Elige momentos que la audiencia del perfil reconozca como suyos: una idea táctica completa, una historia con desenlace, un error con su solución, una afirmación contraintuitiva con su porqué.
- Cada clip debe entenderse sin contexto previo y cerrar lo que abre. Prefiere una idea completa a un instante llamativo que deja la explicación fuera.
- Presenta la lista: número, tramo, primera frase, por qué funciona para esa audiencia, duración aproximada y 2–3 ganchos posibles. Espera su visto bueno antes de renderizar, salvo que ya te haya dicho «haz los que veas».

## 3. Carpeta del trabajo

```
~/ClipsYMids/canales/<slug>/trabajos/<vídeo>/
  <vídeo>.palabras.json        transcripción de la fuente (una vez por vídeo)
  clip-01/trabajo.json         definición editable del clip
  clip-01/subtitulos.json      subtítulos revisados
  clip-01/Clip 01 · <título>.mp4
```

La fuente nunca se modifica ni se mueve. Cada carpeta de clip es su proyecto editable: para cambiarlo se edita el JSON y se vuelve a renderizar.

## 4. Cortes

Aplica `~/ClipsYMids/CORTES.md`. Además, en clips:

- Máximo valor por segundo: si una palabra, explicación o desvío se puede quitar y el clip conserva su significado, lógica, prueba y matiz, se quita.
- El primer segundo da la información táctica o el momento con el que el espectador se identifica. Nunca abras con un conector («y luego», «entonces», «bueno») ni con un punto de una lista («punto número tres»).
- Mueve el inicio y el final al límite de frase que dé ese contexto, aunque se aparte de la marca del usuario, e informa del ajuste.
- Sin duración máxima, salvo que el perfil o el usuario la pidan. Sin música, efectos, B-roll ni llamada a la acción por defecto.

## 5. Definir el clip

`clip-01/trabajo.json` (las rutas pueden ser relativas a ese archivo):

```json
{
  "tipo": "clip",
  "perfil": "../../../perfil.json",
  "fuente": "/ruta/al/video-original.mp4",
  "palabras": "../video-original.palabras.json",
  "tramos": [[734.18, 752.40], [758.02, 781.55]],
  "gancho": {"texto": "El error que hunde\na los canales pequeños", "inicio": 0, "duracion": null},
  "salida": "Clip 01 · El error que hunde canales.mp4"
}
```

- `tramos`: segundos de la fuente, en el orden en que se montan. clipkit ajusta cada borde al fotograma más cercano, igual al generar subtítulos que al renderizar. Un tramo puede ser un objeto con `inicio`, `fin` y opcionalmente `centro_x` (encuadre de recorte para ese tramo) o `ganancia_db`.
- `gancho.texto`: los saltos de línea se respetan; sin saltos, se reparte en líneas equilibradas. `duracion: null` lo mantiene todo el clip.
- `"gancho": false` o `"subtitulos": false` desactivan esos elementos en este clip.
- `"encuadre": {"tipo": "recorte", "centro_x": 0.42}` cambia el encuadre del perfil solo en este clip. Para encontrar dónde está la persona, extrae un fotograma (`clipkit.py fotograma FUENTE.mp4 740 f.png`) y míralo.

## 6. Subtítulos

```bash
python3 ~/ClipsYMids/clipkit.py subtitulos clip-01/trabajo.json
```

Genera `subtitulos.json` con bloques de palabras en el tiempo del clip montado. Revísalo siempre:

- Texto literal, contrastado con el audio (`CORTES.md`, paso 6). Corrige las erratas del reconocimiento sin normalizar lo dicho.
- Marca `"enfasis": true` en la palabra clave de cada bloque cuando la haya: una por bloque, rara vez dos.
- Puedes partir o unir bloques moviendo palabras entre ellos; las líneas se recalculan solas. No cambies tiempos salvo para corregir un error evidente.
- Si regeneras con `--forzar`, se pierden tus correcciones.

## 7. Gancho

- Pocas palabras (orientativo: 4–10), en el lenguaje del espectador.
- Nombra el problema o la promesa que el clip cumple de verdad. Si el clip no paga lo que promete el gancho, cambia el gancho.
- Si el usuario no da gancho, propón 2–3. Si renderizas con el texto por defecto del perfil, ese clip queda como «gancho pendiente» y no se entrega como final.

## 8. Render y revisión

Con Studio elegido, aplica el plan y los textos como elementos editables según `STUDIO.md`; sustituye los renders de clipkit siguientes por fotogramas y renders del proyecto nativo. Verifica el MP4 con clipkit y revisa sus uniones igualmente. Sin Studio, usa este recorrido:

1. Muestra rápida en 1–2 momentos: `clipkit.py render clip-01/trabajo.json --muestra 3.5 --salida m.png`. Mírala: plano completo o bien encuadrado, cara libre, textos legibles a tamaño de móvil, gancho y subtítulos dentro de las zonas seguras.
2. Render completo: `clipkit.py render clip-01/trabajo.json`. Devuelve la duración real, la esperada y los fotogramas esperados.
3. Verificación: `clipkit.py verificar "clip-01/Clip 01 · ….mp4" --esperado <duración esperada> --hoja clip-01/hoja.png`. Debe decodificar entero, sin errores, a unos -14 LUFS (o el objetivo del perfil) y con una diferencia de duración por debajo de 0,05 s. Mira la hoja de fotogramas.
4. Transcribe el MP4 y lee las uniones (`CORTES.md`, paso 5).
5. Corrige lo que encuentres y repite hasta que una pasada completa no encuentre fallos. Cada arreglo puede romper otra cosa: vuelve a mirar la escena entera.

Al entregar, di qué comprobaste y cómo: completo o por muestras, con escucha o sin ella.

## 9. Cambios posteriores

«Cambia el gancho del clip 3», «quita la frase de “bueno, espera”» o «pon el subtítulo en amarillo para este canal»: con clipkit, edita el plan, los subtítulos o el perfil; con Studio, aplica el cambio con su revisión vigente y reconcilia el plan. Renderiza y verifica de nuevo. Un cambio de perfil afecta a los clips futuros; actualiza los ya hechos solo si el usuario lo pide.

## 10. Exporta y sube los clips

La orden autoriza preparar el lote, crear las carpetas de destino, subir, comprobar y, si el perfil lo indica, mover a la Papelera las copias locales ya comprobadas. No autoriza publicar ni programar en redes.

1. **Lote**: solo clips verificados y con gancho real, ordenados por número y nombrados `Clip NN · <título>.mp4`. Si no está claro qué clips entran, pregunta; no incluyas otros por cercanía.
2. **Calendario** (si `entrega.por_dia` está definido): empieza en la fecha que diga el usuario o mañana, en su zona horaria. Reparte N por día consecutivo, fines de semana incluidos; el último día puede quedar parcial (dilo). Antes, revisa lo que ya hay en el destino para no duplicar ni pasar de N en una fecha.
3. **Destino local**: copia a `<carpeta>/AAAA-MM-DD · día de la semana/` (o directamente a la carpeta si no hay calendario).
4. **Destino Drive** (conector o API oficial):
   - Verifica la cuenta y que la carpeta padre existe y se puede escribir.
   - Busca antes de crear para reutilizar las carpetas de fecha. Si hay carpetas con el mismo nombre y no está claro cuál es, pregunta.
   - No cambies permisos de compartir. Si falta acceso, para y avisa; no crees una carpeta alternativa.
5. **Integridad**: compara el tamaño en bytes y el MD5 de cada archivo remoto con el local. Si el conector no da checksum, usa la API o descarga la copia y compárala. Ante una respuesta dudosa (error de red, tiempo agotado), busca primero si el archivo llegó, por tamaño y checksum; nunca reintentes a ciegas, porque crea duplicados.
6. **Limpieza** (solo con `entrega.limpiar_tras_subir: true` y con todo el lote verificado): mueve a la Papelera los MP4 exportados. Conserva la fuente, las carpetas de trabajo (son pequeñas y permiten rehacer) y los recursos. Nunca borres definitivamente ni vacíes la Papelera.
7. **Registro**: guarda `~/ClipsYMids/canales/<slug>/entregas/<fecha>.json` con cada clip, su fecha, su destino (ruta o ID y URL), sus bytes y su MD5. Entrega al usuario los enlaces por día y cuántos clips quedaron verificados.

## Límites

- No publiques ni programes en ninguna red sin una petición expresa para ese envío concreto.
- Instala solo las dependencias comprendidas en el encargo y explicadas al usuario; si falta autorización para una instalación adicional, pide esa elección.
- No subas vídeos ni transcripciones a servicios que el usuario no haya elegido.
~~~~~

### `<skills>/mids-desde-grabaciones/SKILL.md`

~~~~~markdown
---
name: mids-desde-grabaciones
description: Crear «mids» (vídeos horizontales de unos 3–15 minutos que resuelven un problema concreto) a partir de grabaciones largas de cualquier negocio o canal, como consultorías, llamadas con clientes, podcasts, directos o clases. Cubre la selección del problema, cortes precisos, subtítulos del invitado si se configuran, inserciones mínimas con material real, gancho y llamada a la acción, y la ficha de cada mid. Usar cuando pidan «haz un mid», «saca mids de esta grabación» o marquen un tramo como mid. La primera vez configura el canal con preguntas.
---

# Mids desde grabaciones

Un mid es una respuesta completa a un problema concreto, extraída de una grabación larga. Conserva la pregunta, el contexto, el diagnóstico, la solución y la conclusión. Es horizontal (16:9) y suele durar 3–15 minutos. La duración es una referencia: no se estira ni se mutila una solución para cuadrarla.

Funciona porque reaprovecha trabajo que ya ocurre (sesiones con clientes, preguntas en directo, entrevistas) y porque cada pieza específica atrae a un grupo concreto de compradores. Un vídeo sobre un problema muy reconocible puede tener pocas visitas y valer mucho comercialmente. Alcance y rendimiento comercial no son lo mismo.

Herramientas en `~/ClipsYMids/` (`clipkit.py`, `CONFIGURAR.md`, `CORTES.md`). Si falta `clipkit.py`, pide al usuario que vuelva a ejecutar el instalador.

Con `editor.modo: "studio"` en el perfil, lee también `~/ClipsYMids/STUDIO.md`: usa la instalación guardada para crear el montaje con clips y textos nativos, preservando sus cambios manuales. El `trabajo.json` siguiente es el plan y la ficha; no instala el editor sin haberlo elegido.

## 1. Canal, perfil y permiso

- Carga el perfil del canal (`~/ClipsYMids/canales/*/perfil.json`) como en `clips-verticales`. Sin perfil, o sin la sección de mids, sigue `~/ClipsYMids/CONFIGURAR.md`, ronda 4 incluida.
- Mira `mids.privacidad`. Si el consentimiento de los participantes no está confirmado, sigue trabajando, pero marca cada ficha como «permiso pendiente» y recuérdalo al entregar.
- Aplica siempre `privacidad.ocultar`: lo que haya que quitar (apellidos, empresas, cifras privadas, pantallas con datos) se corta o se tapa con una inserción. Nunca se publica «para corregir después».

## 2. Encontrar los mids

Transcribe la grabación entera y léela completa (`CORTES.md`, paso 1). Para cada candidato, comprueba:

- ¿El espectador ideal del perfil reconoce su situación en el inicio?
- ¿Se entiende sin haber visto los minutos anteriores?
- ¿Hay un mecanismo, ejemplo o demostración que justifique la respuesta?
- ¿El cierre resuelve lo que promete el inicio?
- ¿El corte mantiene las condiciones, los matices y el sentido de lo dicho?
- ¿La llamada a la acción continúa el tema de forma natural?

Prefiere una unidad temática completa a un momento llamativo que deja fuera la explicación. Ayuda reconocer en la fuente cuatro tipos de valor: estatus (recursos o posición de quien habla), poder (instrucciones que producen un resultado), credibilidad (pruebas, resultados) y semejanza (la audiencia se reconoce). Una sesión con varias razones o problemas autónomos puede dar varios mids, si cada uno conserva contexto y conclusión.

Si el usuario marcó tramos, respétalos (mismo emparejamiento que en `clips-verticales`). Si no, presenta la lista: tramo, problema, para quién es, promesa, por qué funciona y 2–3 títulos posibles. Espera su visto bueno antes de montar.

## 3. Cortes

La edición de un mid es deliberadamente ligera: abrir donde empieza el problema, cerrar donde queda resuelto y dejar respirar el interior.

- Mueve las marcas al límite de frase que cumpla los criterios anteriores e informa del ajuste.
- Quita saludos, despedidas y logística: buscar datos, compartir pantalla, esperar a alguien o reproducir un vídeo que el ponente resume después. Quita también repeticiones y silencios que no aportan.
- Conserva las pausas que ayudan a comprender y el orden de lo dicho. No recombines frases.
- Precisión de cada borde: `~/ClipsYMids/CORTES.md`.
- Para saber quién habla: el contenido manda. Como pista, quien tiene micrófono propio suena con más graves y brillo que quien llega por Zoom o altavoz; confírmalo siempre leyendo.

Carpeta del trabajo:

```
~/ClipsYMids/canales/<slug>/trabajos/<grabación>/
  <grabación>.palabras.json
  mid-01/trabajo.json
  mid-01/subtitulos.json        (si lleva subtítulos)
  mid-01/fuentes.md             (procedencia de cada inserción)
  mid-01/mid.json               (ficha)
  mid-01/Mid 01 · <título>.mp4
```

## 4. Definir el mid

```json
{
  "tipo": "mid",
  "perfil": "../../../perfil.json",
  "fuente": "/ruta/a/la/grabacion.mp4",
  "palabras": "../grabacion.palabras.json",
  "tramos": [[1203.40, 1388.10], {"inicio": 1391.85, "fin": 1720.30, "ganancia_db": 3.5}],
  "subtitulos_en": [[1203.40, 1290.00], [1455.20, 1502.75]],
  "inserciones": [{"imagen": "img/antes.png", "desde": 42.0, "hasta": 49.5, "modo": "recuadro"}],
  "gancho_video": null,
  "cta_video": "../../../recursos/cta.mp4",
  "salida": "Mid 01 · Por qué nadie compra tu servicio.mp4"
}
```

- `tramos`: segundos de la fuente, en orden. `ganancia_db` sube o baja el volumen de un tramo (ver el paso 7).
- `subtitulos_en`: tramos de la fuente donde va subtitulado, por ejemplo cuando habla el invitado. Con `cuando: "siempre"` en el perfil no hace falta.
- `inserciones`: imágenes en tiempo del cuerpo del mid (sin contar el gancho grabado). `modo`: `completa` (pantalla entera, con bandas si no es 16:9) o `recuadro` (centrada, al 70 % del ancho; `ancho` lo cambia).
- `gancho_video` y `cta_video`: vídeos grabados aparte que se pegan al principio y al final. Pueden tener otra resolución u orientación: se encajan en 16:9 sin deformar.

## 5. Subtítulos

Según `mids.subtitulos.cuando` del perfil:

- `invitado`: solo cuando habla el invitado o cliente, sin las interjecciones del presentador. Marca sus intervenciones en `subtitulos_en`.
- `siempre`: todo el mid.
- `nunca`: sin subtítulos.

Genera con `clipkit.py subtitulos mid-01/trabajo.json` y revisa el texto literal (`CORTES.md`, paso 6). Por defecto van en frases de una línea de hasta unos 44 caracteres, blancas, en negrita y con un contorno fino para que se lean también sobre una captura clara. Llevan al menos 80 px de margen inferior a 1080 p, porque en el móvil la barra de YouTube tapa ese borde.

## 6. Inserciones: lo mínimo y real

Inserta una imagen solo donde el espectador necesita ver algo que se nombra: el trabajo que se revisa, el cambio que se propone, un ejemplo o resultado real. El resto del tiempo, la cámara. Cada inserción debe enseñar algo nuevo: si repite lo que ya enseña otra, sobra.

- Usa material real con procedencia anotada en `fuentes.md`: capturas que aporte el usuario, páginas públicas o el propio trabajo del cliente con su permiso.
- Nunca datos de relleno ni cifras inventadas. Lo hipotético se presenta como hipotético.
- No retoques una captura para que aparente otra cifra. Separa lo que se dijo en la grabación de los datos actuales de una página.

## 7. Sonido

- clipkit normaliza el mid entero al objetivo del perfil (-14 LUFS y pico de -1 dBTP por defecto).
- Si un hablante suena claramente más bajo que otro (es habitual con invitados por Zoom), mide su nivel por pasajes y parte el tramo en el cambio de turno. Busca un mínimo de energía con `clipkit.py bordes` y aplica `ganancia_db` al tramo del más bajo. Diferencias de hasta 2–3 dB no merecen corrección.
- Si la voz baja tanto que no se entiende una frase, descarta esa frase antes que forzar el volumen.

## 8. Gancho, título y llamada a la acción

- **Gancho**: un gancho grabado aparte (`gancho_video`) o la primera frase del propio mid, si ya plantea el problema. No abras con presentaciones.
- **Título**: describe el problema y la promesa que el mid cumple de verdad, con las palabras del comprador. Propón tres. No atraigas clics de un público al que la respuesta no sirve.
- **Miniatura**: la automática es un punto de partida válido. Si el usuario quiere elegir fotograma, extrae candidatos con `clipkit.py render mid-01/trabajo.json --muestra <segundo>`.
- **CTA**: unos 30 s que conectan el problema tratado con un recurso o siguiente paso, con una sola acción clara. Solo con recurso, promesa y enlace reales (los de `mids.cta` del perfil o los que dé el usuario). Si falta algo, el CTA queda pendiente en la ficha; nunca se inventa.

## 9. Render y revisión

Con Studio elegido, aplica el plan según `STUDIO.md`, incluidos gancho, cuerpo y CTA; sustituye los renders de clipkit por los del proyecto nativo. Comprueba el MP4 con clipkit y revisa la transcripción y las uniones igualmente. Sin Studio, usa este recorrido:

1. Muestras en los momentos delicados (inserciones, primer subtítulo): `clipkit.py render mid-01/trabajo.json --muestra <segundo> --salida m.png`. En mids, `--muestra` cuenta los segundos del cuerpo, sin el gancho grabado, y no enseña el gancho ni el CTA: sus uniones se revisan en la hoja de fotogramas y en la transcripción del montaje. Mira las muestras.
2. Render completo: `clipkit.py render mid-01/trabajo.json`.
3. `clipkit.py verificar "mid-01/Mid 01 · ….mp4" --hoja mid-01/hoja.png`: decodificación completa, formato 16:9, sonoridad y hoja de fotogramas.
4. Transcribe el MP4 y léelo entero (`CORTES.md`, paso 5): uniones gramaticales, sin restos de lo quitado y con la promesa del inicio resuelta al final.
5. Si tu entorno permite lanzar un revisor independiente (un subagente), pásale la transcripción del montaje, la lista de cortes con el texto quitado y los subtítulos, y pídele solo fallos con evidencia. Verifica tú cada hallazgo antes de corregir.
6. Repite hasta que una pasada completa no encuentre fallos reales. Al entregar, di qué revisaste y cómo.

## 10. Ficha del mid

Guarda `mid-01/mid.json`:

| Campo | Qué guardar |
| --- | --- |
| `id` y `fuente` | Grabación original, quién habla, sesión y fecha |
| `corte` | Tramos exactos y motivo de la selección |
| `audiencia` | Situación, objetivo y problema concreto de a quién sirve |
| `promesa` | Qué espera el espectador y qué aprende o puede hacer al terminar |
| `titulos` y `cta` | Propuestas de título; recurso, promesa y enlace verificados, o «pendiente» |
| `permiso` | Confirmado, pendiente o no aplica, y qué se ocultó |
| `revision` | Qué se comprobó (sentido, contexto, audio, imagen) y con qué alcance |
| `publicacion` | Cuenta, URL y fecha cuando exista |
| `resultado` | Métrica, ventana temporal, atribución y aprendizaje, cuando haya datos |

Para medir, da a cada mid un ID que conecte grabación, corte, publicación, enlace y resultados (por ejemplo `utm_campaign=mid-007` en el enlace del CTA, si el usuario usa UTM). Las visitas y la retención dicen si llega y entiende la audiencia; los leads, llamadas y ventas atribuibles dicen si sirve al negocio.

## 11. Entrega

Igual que en `clips-verticales` (sección «Exporta y sube los clips»): carpeta local o Drive, comprobación de bytes y MD5, registro en `entregas/` y limpieza solo si el perfil la activa. Los mids no se reparten por días salvo que el usuario lo pida.

## Límites

- No publiques ni programes en YouTube ni en otra plataforma sin una petición expresa para ese envío concreto. Deja todo listo y pide confirmación.
- Respeta la privacidad de los participantes por encima de la productividad.
- Instala solo las dependencias comprendidas en el encargo y explicadas al usuario; pregunta por cualquier instalación adicional.
~~~~~
