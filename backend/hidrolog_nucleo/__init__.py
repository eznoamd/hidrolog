"""Superficie publica do nucleo do Hidrolog para os plugins de sensor.

    from hidrolog_nucleo.plugin import Plugin, Manifesto, Campo, Regra, Aba, ...

Um plugin so deveria importar daqui (e de bibliotecas proprias): o resto do
backend (pacote `app`) e interno e pode mudar sem aviso. O contrato tem
versao (VERSAO_CONTRATO, SemVer): capacidade opcional nova e versao menor;
assinatura que muda e versao maior.
"""
