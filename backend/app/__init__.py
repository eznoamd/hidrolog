"""
Backend local do Hidrolog, app de dados de sensores ambientais. Cada tipo de
sensor e um plugin, em repositorio proprio; o app nao traz nenhum.

O app desktop chama a camada de servico direto (app.servico e as consultas
de cada plugin, ex. hidrolog_<sensor>.consultas); a API FastAPI
(app.api.main) e uma casca fina opcional, so em 127.0.0.1.
"""
