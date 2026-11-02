# Criar um plugin (desenvolvedores)

Este tópico é um resumo para quem programa em Python. O guia completo, com código, está no
repositório do Hidrolog, junto do plugin de exemplo (`exemplos/plugin-termometro`, arquivo
`COMO-CRIAR-UM-PLUGIN.md`); o exemplo é um ponto de partida pronto para copiar.

## O que um plugin declara

| Parte | Para quê |
|---|---|
| `hidrolog-plugin.toml` | o manifesto: código, nome, versão, contrato, autor, tabelas e campos do cadastro. É lido **sem executar código**, para a tela de confirmação. |
| Tabela e migração | onde as leituras ficam no banco, com uma chave única que evita duplicatas. |
| Ingestão | `reconhecer` (olha só os nomes dos arquivos e decide se o envio é deste sensor) e `ler` (devolve uma leitura por vez). |
| Ficha | os campos do cadastro do equipamento e a validação deles. |
| Regras | as regras de qualidade e seus parâmetros ajustáveis. |
| Consultas e exportação | o que as abas leem e os formatos de arquivo. |
| Interface | as abas da página do equipamento (o único módulo que usa a interface gráfica). |

O plugin só usa o **contrato** do núcleo (`hidrolog_nucleo.plugin`). O resto do app é interno e
pode mudar entre versões.

## O que o núcleo faz por você

Abrir `.zip`, `.rar` e pastas; gravar em lotes numa transação; deduplicar; mostrar o progresso;
cancelar; rodar as regras; registrar o envio; aplicar as migrações com cópia de segurança; e
montar a página do equipamento com período e as abas comuns.

## Testar

O **kit de conformidade** confere o plugin contra o contrato, usando a amostra de dados que vem
com ele. De dentro do repositório do plugin:

```
../hidrolog/frontend/venv/bin/python -m pytest --plugin=<codigo>
```

Quando o kit passa, empacote a pasta em `.zip` (ou publique uma tag no GitHub) e instale pelo
gerenciador (veja [Plugins de sensor](ajuda:plugins)).
