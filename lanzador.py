"""Punto de entrada del .exe (PyInstaller): arrastrar una carpeta encima equivale a `cronica <carpeta>`."""
import sys

from cronica.cli import main

sys.exit(main())
