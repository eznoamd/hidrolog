"""Ponto de entrada: `python -m hidrolog [--tema claro|escuro]`."""

import multiprocessing
import sys

if __name__ == "__main__":
    # o backend interpreta os arquivos num pool de processos ("spawn"); num app
    # congelado (PyInstaller) os processos filhos voltam por aqui
    multiprocessing.freeze_support()
    from hidrolog.aplicacao import main

    sys.exit(main())
