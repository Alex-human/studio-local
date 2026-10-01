# Studio Local

Editor de vídeo para Mac pensado para trabajar con Claude: cortes al fotograma, gráficos, mezcla de audio, comentarios sobre el fotograma y exportación, todo en tu ordenador. Claude lo controla por código y tú revisas en la app.

## Instalarlo con Claude

No hace falta saber programar ni usar GitHub.

1. Instala [Claude Code](https://claude.com/claude-code) (la app de escritorio sirve).
2. Abre Claude en cualquier carpeta de tu Mac y pégale esto:

   > Descarga el repositorio https://github.com/Alex-human/studio-local en mi carpeta de usuario, lee su ONBOARDING.md y sigue sus pasos para instalar Studio Local en este Mac.

3. Acepta los permisos que te pida. Al terminar, Claude abre Studio y te explica cómo usarlo.

Requisitos: un Mac con chip Apple (M1 o posterior), conexión a internet durante la instalación y unos 500 MB libres. Claude instalará las herramientas de línea de comandos de Apple si faltan.

## Qué incluye

- Biblioteca de proyectos con miniaturas y carpetas.
- Cortes al fotograma que mueven a la vez voz, gráficos, efectos y subtítulos, con música que puede seguir sonando continua.
- Imágenes pegadas desde el portapapeles, superposición de vídeo, títulos animados y subtítulos.
- Volumen por pista y por elemento, fundidos y reducción de música mientras hablas.
- Comentarios sobre el fotograma (⌘F) que Claude puede leer y aplicar.
- Exportación en H.264 a `~/Movies/Studio Local`.
- CLI y servidor MCP para que Claude edite los mismos proyectos mientras tú miras.
- Interfaz opcional para el iPhone.

## Cambiarlo a tu gusto

Abre Claude en la carpeta del repositorio y pídele el cambio. `CLAUDE.md` le dice dónde está cada parte y cómo comprobarla; el manual completo está en [`docs/MANUAL.md`](docs/MANUAL.md).

## Licencia

MIT. Los archivos de terceros conservan su licencia: la tipografía Inter (OFL), SoundTouchJS (MPL-2.0) y el sonido de clic (CC0). FFmpeg se instala desde `imageio-ffmpeg` con su propia licencia. La LUT de DJI para D-Log M no se incluye; ver [`editor/assets/luts/README.md`](editor/assets/luts/README.md).
