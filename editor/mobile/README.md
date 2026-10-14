# Studio en el iPhone

Interfaz opcional para revisar y editar los mismos proyectos del Mac: cortes, bordes, eliminación, textos y comentarios con dibujo. Tocar el timeline pausa y sitúa el vídeo; arrastrar sus tiradores ajusta los bordes. Reescribe un gancho o subtítulo tocándolo en el vídeo o con **Reescribir**. La velocidad de revisión 1×–3× no cambia el montaje ni su exportación. Todas las ediciones conservan revisión e historial; no modifican las fuentes.

## Abrirlo

`../mobile.command` escucha en `127.0.0.1:8766`; abre `http://127.0.0.1:8766` en el Mac. Para una prueba independiente usa `--projects /ruta/a/fixtures --port 8767`. La app del Mac funciona sin este servidor.

Fuera de casa, configura Tailscale en Mac e iPhone con la misma cuenta, Serve HTTPS privado hacia el puerto local y el servidor con `--origin https://NOMBRE.ts.net --user CUENTA`. Exige ese Host y la identidad que incorpora Serve. No uses Funnel ni un proxy que permita falsificarla. El Mac debe estar encendido, despierto y conectado; la interfaz usa WebCodecs/Web Audio y necesita un navegador compatible. El primer acceso y los permisos los completa el usuario.

Si eliges arranque automático, crea un LaunchAgent de usuario que ejecute `mobile.command` con esos argumentos y reinicie al salir. El proceso comprueba cambios de su Python y del motor cada veinte segundos y sale sin interrumpir una escritura para que el supervisor cargue el código nuevo. Sin supervisor, vuelve a arrancarlo manualmente. Los archivos de interfaz se leen del disco.

## Reproducción y recursos

El navegador descodifica con WebCodecs los tramos H.264 y compone imagen, textos canónicos y capas con un reloj Web Audio. Evita arrancar un elemento de vídeo en cada corte. Escritorio pide hasta 1920 píxeles; móvil, 1280, y baja a 640 si la conexión no sostiene la reproducción. Fuentes pequeñas no se amplían. Cada calidad tiene su caché; el audio conserva tiempos y se reutiliza.

El Mac prepara solo los tramos de fuente usados, de diez segundos, con prioridad para cabezal y minuto siguiente, después el montaje abierto y por último la biblioteca. Son dos trabajadores y una preparación de fondo; la caché móvil admite 6 GiB. Cortes y cambios de texto reutilizan medios. El audio va en MP4 compatible con WebKit y SoundTouch conserva su tono a mayor velocidad; arranque y pausa tienen fundidos y compensación de latencia. Ocultar o abandonar el montaje libera los recursos de reproducción.

Las esperas de descarga, descodificación o activación de audio tienen límite y aviso. Sin WebCodecs o ante fallos del decoder, se ofrece composición canónica por tramos. El cambio de reproductor puede requerir recargar una página abierta. La conexión y el navegador reales determinan el resultado; una prueba en WebKit del Mac no certifica el iPhone físico.

## Ediciones y comentarios

La última imagen permanece hasta mostrar la revisión nueva. Las acciones usan identificador persistente: una respuesta perdida no repite un corte. Si una escritura queda incierta, relee el proyecto antes de reenviar; conflictos y comentarios conservan el borrador. Deshacer comparte historial con el Mac y puede deshacer su última acción.

`server.py` adapta operaciones limitadas al motor. HTML, JavaScript y SoundTouchJS 2.1.1 (MPL-2.0) se sirven localmente, sin CDN. `.runtime/` guarda logs y caché regenerable, nunca fuentes. El acceso remoto se configura aparte y no lo habilita el instalador de contenido por defecto.

## Comprobar

`../.venv/bin/python3 -m unittest discover -s ../tests -p test_mobile.py -v`; con Node, `../tests/ui_mobile.cjs` y `../tests/ui_direct.cjs`. Usan medios sintéticos y bibliotecas temporales. Las comprobaciones reales de sockets locales y VideoToolbox requieren acceso a esos servicios de macOS; no se sustituyen por un render por software para declarar probado ese recorrido.
