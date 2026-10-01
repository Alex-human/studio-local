# Onboarding de Studio Local

Instrucciones para Claude. La persona que te las pasa quiere tener Studio Local funcionando en su Mac sin tocar la terminal. Hazlo tú, paso a paso, y explícale en lenguaje sencillo lo que vas haciendo. Pide permiso antes de cada comando que instale algo.

## 1. Comprobar el Mac

- `sw_vers -productVersion` y `uname -m`. Studio Local necesita un Mac con chip Apple (`arm64`). Si es Intel, díselo y no sigas.
- `xcode-select -p`. Si falla, ejecuta `xcode-select --install`, dile que acepte la ventana que aparece y espera a que termine antes de seguir. Esas herramientas traen `git`, `swiftc` y Python.

## 2. Descargar el repositorio

Si aún no estás dentro de este repositorio, clónalo en su carpeta de usuario (o donde te diga):

```
git clone https://github.com/Alex-human/studio-local.git ~/studio-local
```

Trabaja desde esa carpeta en el resto de pasos.

## 3. Instalar

Ejecuta `./setup.command`. Tarda uno o dos minutos y necesita internet:

- crea el entorno de Python `editor/.venv` con Pillow, NumPy e imageio-ffmpeg;
- enlaza FFmpeg en `editor/runtime/ffmpeg`;
- compila y firma la app `editor/Studio Local.app`.

Se puede repetir sin riesgo. Si un paso falla, lee el error, corrígelo y vuelve a lanzarlo. Los avisos de compilación sobre APIs obsoletas son normales.

## 4. Comprobar que funciona

- `editor/.venv/bin/python3 -m unittest discover -s editor/tests -p 'test_*.py'` debe terminar en `OK`. Algunas pruebas usan los servicios multimedia de macOS: si fallan solo por permisos de un entorno aislado, repítelas fuera de él.
- Crea un proyecto de prueba con la CLI para confirmar que el motor responde:

```
echo '{"action":"list"}' > /tmp/studio-list.json && ./editor/studio-cli --request-file /tmp/studio-list.json
```

Debe devolver `"ok": true`.

## 5. Abrir Studio

Ejecuta `./editor/studio.command`. La primera vez se abre **Tus proyectos**, vacío. Enséñale:

- **＋ Nuevo proyecto** crea un montaje; **Medios** añade vídeos, música y efectos. Los vídeos originales no se copian ni se modifican: no los mueva mientras los use.
- Para cortar: ⌘C al principio y al final del error, y Supr. **Espacio** reproduce, ⌘Z deshace y todo se guarda solo.
- **⌘F** deja un comentario sobre el fotograma. Después puede decirte «aplica mi feedback» y tú lo lees con la acción `feedback` de la CLI.
- **Exportar** guarda el vídeo final en `~/Movies/Studio Local`.

Sugiérele que añada `editor/Studio Local.app` al Dock.

## 6. Cómo editas tú sus vídeos

Lee `docs/MANUAL.md`, sobre todo «Control por código» y «Edición simultánea». Las reglas básicas:

- usa siempre `editor/studio-cli` con `open` y después `ops` con la `revision` leída; nunca reescribas un `.studio` entero;
- los intervalos van en fotogramas, `[inicio, fin)`;
- comprueba el resultado con `frame` o con un `render` de un tramo (`range`) antes de decir que algo está hecho;
- no exportes el vídeo entero si no te lo pide.

## 7. Opcional

- **Vídeos en D-Log M de DJI:** sigue `editor/assets/luts/README.md`.
- **iPhone:** sigue `editor/mobile/README.md`. Necesita Tailscale en el Mac y en el iPhone.
- **Cambiar el editor:** cualquier cambio de código va seguido de las pruebas y de `./editor/build.command`. Si la app está abierta, la actualización se instala sola al pausar.

## 8. Cerrar

Resume en pocas líneas lo que instalaste, dónde están los proyectos (`editor/projects`) y las exportaciones (`~/Movies/Studio Local`), y qué comprobaciones pasaron. Si alguna quedó pendiente, dilo.
