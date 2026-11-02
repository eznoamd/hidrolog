# Instalação, dados e cópias de segurança

## Onde ficam os dados

Tudo fica numa pasta de dados do usuário do sistema:

- Linux: `~/.local/share/Hidrolog/`
- Windows: `%LOCALAPPDATA%\Hidrolog\`
- macOS: `~/Library/Application Support/Hidrolog/`

A variável de ambiente `HIDROLOG_DADOS_DIR` troca essa pasta. Dentro dela:

| Arquivo | Conteúdo |
|---|---|
| `hidrolog.db` | o banco (SQLite) com usuários, equipamentos, envios e leituras |
| `hidrolog.log` | o registro de erros com os detalhes técnicos |
| `hidrolog-interface.ini` | preferências da interface deste computador (tema) |
| `plugins/` | os plugins instalados pelo gerenciador |
| `marca/` | o nome e as logos do laboratório e da instituição |

## Cópias de segurança

Antes de aplicar mudanças de estrutura de um plugin, o app faz sozinho uma cópia do banco. Mesmo
assim, faça cópias regulares: com o app **fechado**, copie o arquivo `hidrolog.db` para outro
disco. Para restaurar, feche o app e coloque a cópia no lugar.

## Criar o master e recuperar a senha dele

Com o app instalado, na pasta do backend:

```
python -m app criar-master --login admin --nome "Seu nome"
python -m app redefinir-senha --login admin
```

O primeiro só funciona se ainda não houver master. O segundo serve para qualquer usuário e exige
acesso ao arquivo do banco: quem tem acesso ao computador tem acesso aos dados.

## Nome e logos do laboratório

Sem configuração, o app é genérico: aparece só "Hidrolog" e o texto **LOGO** no lugar das
logos. Para personalizar, crie na pasta `marca/` um arquivo `marca.toml`:

```toml
[laboratorio]
sigla = "LAB"
nome = "Laboratório de Exemplo"

[instituicao]
sigla = "UNI"
nome = "Universidade de Exemplo"
```

e ponha ao lado as imagens: `logo.png` (e `logo-escura.png` para o tema escuro) e
`instituicao.svg`. O nome da instituição também vai para os metadados dos arquivos exportados.
Reinicie o app para aplicar.
