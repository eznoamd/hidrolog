"""Ponto de entrada do Hidrolog.exe (PyInstaller).

    Hidrolog.exe                          abre o app
    Hidrolog.exe admin <comando> ...      linha de comando do backend
                                          (ex.: admin criar-master --login admin --senha-arquivo x.txt)
    Hidrolog.exe --autoteste [arquivo] [--plugin PASTA]
                                          confere o pacote sem abrir janela (usado no CI)

O executável é de janela (sem console). Nos comandos "admin", ele se liga ao
console de quem o chamou (Prompt de Comando ou PowerShell), para mostrar a
saída e pedir a senha.
"""

import multiprocessing
import sys


def _usar_console_de_quem_chamou() -> None:
    if not sys.platform.startswith("win"):
        return
    import ctypes

    if ctypes.windll.kernel32.AttachConsole(-1):        # ATTACH_PARENT_PROCESS
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stdin = open("CONIN$", encoding="utf-8")


def principal() -> int:
    # o backend usa processos "spawn"; os processos filhos voltam por aqui
    multiprocessing.freeze_support()
    argumentos = sys.argv[1:]
    if argumentos[:1] == ["admin"]:
        _usar_console_de_quem_chamou()
        from app.__main__ import main as linha_de_comando

        return linha_de_comando(argumentos[1:])
    if argumentos[:1] == ["--autoteste"]:
        from hidrolog.autoteste import principal as autoteste

        return autoteste(argumentos[1:])
    from hidrolog.aplicacao import main

    return main()


if __name__ == "__main__":
    sys.exit(principal())
