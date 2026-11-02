# Spec do PyInstaller: gera dist/Hidrolog/ com Hidrolog.exe e tudo de que ele
# precisa. Rodar de dentro de instalador/:   pyinstaller --noconfirm hidrolog.spec
# (o backend, o design e o frontend precisam estar instalados no ambiente).

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# dados que o código lê do disco
datas = []
# migrações do Alembic: são lidas como arquivos .py (env.py, versions/) e o modelo .mako
datas += collect_data_files("app", include_py_files=True,
                            includes=["nucleo/migracoes/*.py", "nucleo/migracoes/*.mako",
                                      "nucleo/migracoes/versions/*.py"])
datas += collect_data_files("design")                                   # fontes, ícones, estilos dos gráficos
datas += collect_data_files("hidrolog", includes=["ajuda/topicos/*.md"])  # Central de ajuda
datas += collect_data_files("matplotlib")

hiddenimports = []
for pacote in ("app", "hidrolog_nucleo", "hidrolog", "design"):
    hiddenimports += collect_submodules(pacote)
hiddenimports += ["sqlalchemy.dialects.sqlite", "alembic.runtime.migration", "alembic.ddl.sqlite",
                  "argon2", "rarfile", "netCDF4", "cftime", "matplotlib.backends.backend_qtagg"]

# os plugins entram depois, pelo gerenciador, e podem usar módulos que o app em si
# nunca importa: a biblioteca padrão mais comum vai junto (ver COMO-CRIAR-UM-PLUGIN.md)
hiddenimports += [
    "csv", "json", "statistics", "decimal", "fractions", "zipfile", "gzip", "bz2", "lzma", "tarfile",
    "struct", "uuid", "hashlib", "base64", "binascii", "configparser", "tomllib", "sqlite3", "calendar",
    "zoneinfo", "xml.etree.ElementTree", "xml.dom.minidom", "html", "textwrap", "string", "difflib",
    "bisect", "heapq", "array", "copy", "pprint", "fnmatch", "glob", "shutil", "tempfile", "unicodedata",
]

a = Analysis(
    ["entrada.py"],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Hidrolog",
    console=False,          # app de janela; "Hidrolog.exe admin ..." se liga ao console de quem chamou
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Hidrolog", upx=False)
