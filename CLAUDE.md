# Studio Local

- Si Studio Local aún no está instalado en este Mac (falta `editor/.venv` o `editor/Studio Local.app`), sigue `ONBOARDING.md`.
- Para usar o cambiar el editor, lee `docs/MANUAL.md`. El motor está en `editor/engine` (Python), la interfaz en `editor/ui` (HTML y JavaScript) y la app nativa en `editor/native` (Swift).
- Edita los proyectos con `editor/studio-cli` y operaciones con `revision`. Nunca reescribas un `.studio` entero ni modifiques los vídeos originales.
- Después de cambiar código, ejecuta las pruebas (`editor/.venv/bin/python3 -m unittest discover -s editor/tests -p 'test_*.py'`) y vuelve a compilar con `./editor/build.command` (`--interface` si solo cambiaste `editor/ui`).
