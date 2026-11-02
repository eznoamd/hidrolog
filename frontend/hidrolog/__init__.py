"""Hidrolog: app desktop (PySide6) para cadastrar e consultar
os dados dos sensores ambientais.

O front chama a camada de serviço do backend direto (`app.servico`), sem
HTTP, e usa o tema e os componentes de `design`. As telas de cada tipo de
sensor vêm do plugin dele (pacote único em `../plugins/<codigo>`, módulo
`Plugin.interface`).

    python -m hidrolog
"""

VERSAO = "0.1.0"
