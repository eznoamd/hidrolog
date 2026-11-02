"""Erros da camada de servico. `status` e o codigo HTTP equivalente (a API
so traduz; o app desktop pode mostrar str(erro) direto)."""


class ErroServico(Exception):
    status = 400


class ErroAutenticacao(ErroServico):
    """Login ou senha errados, ou usuario desativado."""
    status = 401


class ErroPermissao(ErroServico):
    """O perfil do usuario nao permite a operacao."""
    status = 403


class NaoEncontrado(ErroServico):
    status = 404


class ErroValidacao(ErroServico):
    """Valores invalidos num formulario. `campos`: {campo: mensagem}, para a
    interface mostrar o erro ao lado de cada campo."""
    status = 422

    def __init__(self, mensagem: str, campos: dict | None = None):
        super().__init__(mensagem)
        self.campos = dict(campos or {})


class ErroEnvio(ErroServico):
    """Envio rejeitado (arquivo invalido, path traversal, etc.)."""
    status = 400


class EnvioRecusado(ErroEnvio):
    """O plugin do sensor recusou o envio (estrutura diferente da esperada)."""
    status = 422


class LimiteExcedido(ErroEnvio):
    """Passou do limite de tamanho/quantidade (protecao contra zip bomb)."""
    status = 413


class ErroRarSemFerramenta(ErroEnvio):
    """RAR comprimido e nenhum programa para descompactar instalado."""
    status = 422


class Conflito(ErroServico):
    status = 409
