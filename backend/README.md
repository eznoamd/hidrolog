# backend

O backend é a parte do Hidrolog que guarda e trata os dados, sem nenhuma interface. É ele quem
abre o banco, confere quem está usando o app e o que essa pessoa pode fazer, recebe os arquivos
dos sensores, grava as leituras sem duplicar, roda as regras de qualidade, gera as exportações e
administra os plugins. O app desktop, a API local e a linha de comando são só jeitos diferentes de
chegar até ele: toda a lógica mora aqui, uma vez só.

Uma ideia guia tudo nesta pasta: o backend não conhece nenhum sensor. Ele sabe lidar com
"equipamentos", "envios" e "leituras" de forma genérica, e pergunta ao plugin de cada tipo de
sensor o que é específico (que arquivos são dados, como lê-los, onde guardá-los, que regras
valem). Por isso o mesmo núcleo serve a um pluviômetro, a uma estação meteorológica ou a qualquer
aparelho que ainda vá existir.

## Estrutura

```
backend/
├── app/                      pacote "app": o núcleo do Hidrolog
│   ├── servico.py            a camada de serviço: todas as operações que o resto do sistema chama
│   ├── config.py             configuração (variáveis de ambiente, pasta de dados, marca)
│   ├── __main__.py           linha de comando (python -m app ...)
│   ├── nucleo/               as engrenagens por trás do serviço
│   │   ├── modelos.py        tabelas do núcleo (SQLAlchemy)
│   │   ├── banco.py          conexão, sessões, migrações e cópia de segurança antes de migrar
│   │   ├── migracoes/        migrações do núcleo (Alembic)
│   │   ├── extracao.py       abre o envio: pastas, .zip, .rar, com as proteções
│   │   ├── ingestao.py       conversa com o plugin e grava as leituras
│   │   ├── paralelo.py       pool de processos para ler muitos arquivos
│   │   ├── regras.py         motor das regras de qualidade
│   │   ├── plugins.py        descoberta e registro dos plugins
│   │   ├── gerenciador.py    instalar, atualizar, desativar e voltar versão de plugins
│   │   ├── seguranca.py      senhas (argon2) e perfis
│   │   ├── administracao.py  criar o master e redefinir senha (só pela linha de comando)
│   │   └── tipos.py, erros.py   o que o serviço devolve e as exceções
│   └── api/                  API HTTP local (FastAPI), opcional
├── hidrolog_nucleo/          o contrato dos plugins
│   ├── plugin.py             as classes que um plugin usa para se descrever
│   └── testes/               kit de conformidade (plugin do pytest)
└── tests/                    testes, com um sensor fictício e plugins mínimos
```

O pacote **`app`** é o núcleo propriamente dito. Dentro dele, `servico.py` é a única porta que o
resto do sistema deveria usar: cada função recebe o usuário que está logado, confere o perfil
dele no banco e faz o trabalho, devolvendo objetos simples (dataclasses de `tipos.py`), nunca
objetos do banco. Tudo o que fica em `app/nucleo/` é interno e pode mudar livremente, porque
ninguém de fora o chama direto.

O pacote **`hidrolog_nucleo`** é o oposto: é pequeno, estável e público. Ele contém o contrato
(`plugin.py`), isto é, as classes com que um plugin diz o que sabe fazer (`Plugin`, `Manifesto`,
`Ingestao`, `Campo`, `Regra`, `Aba`, `Exportacao` e as estruturas que circulam entre núcleo e
plugin). Um plugin importa só daqui; assim o núcleo pode evoluir sem quebrar os sensores
existentes, e uma mudança incompatível vira uma nova versão do contrato (`VERSAO_CONTRATO`).

A pasta **`tests/`** testa tudo pela camada de serviço, com bancos temporários. Como o repositório
não traz nenhum sensor real, os testes usam um sensor fictício (`tests/sensor_estacao`, com os
dados sintéticos de `tests/dados`), alguns plugins mínimos para casos específicos e o plugin de
exemplo de `../exemplos/plugin-termometro`.

## Funcionamento

### Banco de dados

Tudo fica num único arquivo SQLite, na pasta de dados do usuário: as tabelas do núcleo (usuários,
tipos de sensor, equipamentos, envios, plugins instalados, auditoria, configuração das regras e
ocorrências) e as tabelas de leituras de cada plugin. O SQLite foi escolhido por combinar com um
app de um computador só: não tem servidor nem administração, e o banco inteiro é um arquivo que
se copia para fazer backup. A conexão liga o modo WAL, para que consultas não travem durante uma
importação, e as chaves estrangeiras. O modelo usa só tipos genéricos do SQLAlchemy 2, então
trocar de banco é uma questão de configurar `DATABASE_URL` (ainda não testado com outro banco).

A estrutura do banco evolui por migrações do Alembic, montadas em código (não há `alembic.ini`).
O núcleo tem a sua sequência de migrações e cada plugin traz a dele, num ramo separado com o
código do plugin. Ao abrir, o app sobe tudo o que estiver pendente; antes de aplicar migrações de
um plugin num banco que já existe, ele copia o arquivo do banco para o lado
(`hidrolog.backup-<data>-antes-migrar-<revisões>.db`) e registra isso na auditoria. As migrações
de um plugin desativado continuam conhecidas, para que os dados dele fiquem intactos.

### Importação em três camadas

Importar é a operação central, e ela é dividida entre núcleo e plugin. Primeiro o núcleo **abre**
o envio, seja uma pasta, arquivos soltos, um `.zip` (inclusive um zip dentro de outro, até dois
níveis) ou um `.rar`, e monta uma árvore com nomes e tamanhos, sem ler o conteúdo. Depois o plugin
**reconhece** essa árvore: olhando só os nomes, ele devolve um plano (quais arquivos são leituras,
quais ignorar e por quê) ou recusa o envio dizendo o motivo, e nesse caso nada é gravado. Por fim
o plugin **lê** cada unidade do plano, devolvendo uma leitura por vez, enquanto o núcleo **grava**
em lotes, dentro de uma única transação, descartando o que já existe no banco pela chave natural
que o plugin declarou (normalmente equipamento e horário). Por isso reimportar o mesmo cartão SD
não duplica nada.

Durante a importação o núcleo informa o progresso (examinando, interpretando, gravando) e aceita
ser cancelado: se quem chamou interromper, a transação é desfeita e nenhum dado fica pela metade.
Se o plugin permitir, as unidades são lidas em paralelo num pool de processos, o que importa um
cartão de ~11 mil arquivos em cerca de 8 segundos. Leituras que o plugin não conseguiu
interpretar são guardadas marcadas como corrompidas, para diagnóstico, e não entram nas
consultas nem nas exportações. Se os dados trouxerem um número de série diferente do cadastrado,
o envio entra com um aviso; se o equipamento ainda não tinha número de série, o primeiro que
aparecer é registrado.

Como os arquivos vêm de fora, a abertura é defensiva. Nada é extraído para o disco: o plugin lê
cada arquivo direto do compactado. Caminhos absolutos, letras de unidade ou `..` dentro de um zip,
de um rar ou do nome de um upload recusam o envio inteiro. Há limites para o total de bytes
descompactados, para o tamanho de cada arquivo e para a quantidade de arquivos, contados sobre o
que é realmente descompactado, o que protege contra "zip bombs". Arquivos que o plugin ignora nem
chegam a ser descompactados. Arquivos `.rar` comprimidos precisam de um programa no sistema
(`unrar`, `unar` ou `bsdtar`); sem ele, o envio falha com uma mensagem que diz o que instalar.

### Qualidade

Depois de cada importação, o motor de regras aplica as regras de qualidade que o plugin declarou,
em três níveis: por leitura (por exemplo, um valor acima do limite físico), por envio (lacunas no
período importado) e por equipamento (sem dados há muitos dias, bateria baixa), estas também
reavaliadas a cada abertura do app. Uma regra pode ser declarativa (coluna, operador e limite) ou
uma função do plugin. Os parâmetros têm valores padrão do plugin e podem ser ajustados por
equipamento, ficando registrado quem mudou e quando. O resultado são ocorrências (alerta, suspeita
ou aviso) guardadas numa tabela própria: as regras rodam dentro de um savepoint que é sempre
desfeito, então nenhuma regra, nem uma com defeito, consegue alterar ou apagar leituras.

### Plugins

O núcleo encontra os plugins em duas fontes. Pacotes Python instalados que declaram o entry point
`hidrolog.plugins` (o caminho do desenvolvimento, com `pip install -e`) e a pasta `plugins/` dentro
da pasta de dados, onde o gerenciador instala o que o master importa pelo app. Cada plugin é
conferido antes de entrar: contrato compatível, código único, módulo importável. Um plugin com
problema não é carregado, os dados dele continuam no banco e o motivo aparece na tela de plugins.

O gerenciador (`gerenciador.py`) instala a partir de uma pasta, de um `.zip` ou de um repositório
do GitHub (por tag). Ele lê o manifesto `hidrolog-plugin.toml` sem executar nada do plugin, mostra o
que vai entrar, exige a senha do master (três tentativas) e só então copia o pacote para a pasta
de plugins, guardando as versões anteriores para permitir voltar atrás. Desativar e reativar
também pedem a senha. Tudo, inclusive as tentativas recusadas, vai para a tabela de auditoria, e
as mudanças valem ao reiniciar o app.

### Usuários e perfis

Há três perfis encaixados: `leitura` (consulta e exporta), `cadastro` (também cadastra
equipamentos, importa e trata a qualidade) e `master` (também administra usuários e plugins). As
senhas são guardadas com argon2id. O master nunca é criado pelo app: ele nasce pela linha de
comando (`python -m app criar-master`) e o app não consegue rebaixá-lo nem desativá-lo, para que
ninguém se tranque para fora. A conferência de perfil a cada chamada protege contra erros de uso
e contra a interface errada; ela não é uma barreira contra código rodando no mesmo processo, que
poderia abrir o arquivo do banco direto.

### Exportação

O núcleo só conhece a ideia de "formato" (código, nome, extensão). Cada plugin declara os seus e
escreve o arquivo, recebendo do núcleo o equipamento, uma função que diz a qualidade de cada
leitura (para a coluna de qualidade) e o nome da instituição, tirado da pasta de marca, para os
metadados. O núcleo escreve num nome temporário e só renomeia no fim, então uma falha nunca deixa
arquivo pela metade. Um equipamento cujo plugin não está carregado continua exportável por um CSV
genérico com todas as colunas da tabela.

## Integração com o sistema

O **frontend** importa `app.servico` e chama as funções direto, no mesmo processo, sem HTTP, em
threads de trabalho para o que demora. Os **plugins** implementam o contrato de `hidrolog_nucleo`
e são chamados pelo núcleo; para as consultas próprias deles (as que as abas usam), o plugin
oferece um módulo que o app obtém com `plugins.obter(codigo).modulo_consultas()`.

```python
from app import servico

servico.iniciar()                                   # abre e migra o banco (uma vez)
usuario = servico.autenticar("ana", "senha")
eq = servico.criar_equipamento(usuario, "pluviometro", "Pluviômetro telhado")
resumo = servico.importar_caminho(usuario, eq.id, "/media/ana/SD")
print(resumo.novas, resumo.duplicadas, resumo.corrompidas)
servico.exportar(usuario, eq.id, None, None, "csv", "/home/ana/Downloads")
servico.encerrar()
```

A **linha de comando** cobre a administração que não existe na interface (criar o master,
redefinir senha esquecida, migrar) e serve para scripts:

```bash
venv/bin/python -m app criar-master --login admin --nome "Ana"
venv/bin/python -m app redefinir-senha --login ana
venv/bin/python -m app importar --login ana --equipamento 1 /media/SD
venv/bin/python -m app nova-migracao --sensor pluviometro -m "nova coluna"
venv/bin/python -m app servidor                       # a API, sempre em 127.0.0.1
```

A **API local** (`app/api/`) é uma casca fina sobre o serviço, pensada para uma futura interface
web. Ela só escuta em `127.0.0.1`, autentica por token (guardado na memória, válido por 12 h) e
tem documentação interativa em `http://127.0.0.1:8000/docs`. Além das rotas do núcleo (login,
usuários, equipamentos, envios por upload ou caminho local, exportação, saúde), cada plugin pode
acrescentar as suas, com o código dele como prefixo.

## Execução e testes

```bash
cd backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m pytest
```

Os testes não precisam de tela, de internet nem de nenhum plugin real. Eles cobrem a importação
em todas as formas de envio, a deduplicação, as proteções contra arquivos maliciosos, o RAR (com
um gerador próprio de arquivos `.rar`, já que o programa `rar` não é livre), as permissões dos
três perfis, as regras de qualidade, a exportação, o gerenciador de plugins (inclusive reabrindo o
app num processo novo) e o kit de conformidade. O mesmo kit serve para qualquer plugin, rodado de
dentro do repositório dele: `pytest --plugin=<codigo>`.

## Referência

**Variáveis de ambiente** (todas opcionais):

| Variável | Padrão | Para quê |
|---|---|---|
| `HIDROLOG_DADOS_DIR` | pasta de dados do usuário | onde ficam o banco, os backups, os plugins e a marca |
| `DATABASE_URL` | SQLite em `HIDROLOG_DADOS_DIR` | outro banco |
| `HIDROLOG_PROCESSOS` | `min(4, CPUs)` | processos para ler os arquivos (1 = sem paralelismo) |
| `HIDROLOG_MAX_DESCOMPACTADO_MB` | 2048 | limite de bytes lidos num envio |
| `HIDROLOG_MAX_ARQUIVO_KB` | 1024 | limite de cada arquivo de dados |
| `HIDROLOG_MAX_ARQUIVOS` | 500000 | limite de arquivos num envio |
| `HIDROLOG_SENHA` | pergunta no terminal | senha para a linha de comando, em scripts |

**Funções da camada de serviço** (`app.servico`), pelo perfil mínimo:

| Assunto | Funções | Perfil |
|---|---|---|
| Sessão | `iniciar`, `encerrar`, `existe_master`, `autenticar` | — |
| Própria conta | `alterar_meu_nome`, `trocar_minha_senha`, `meus_envios` | leitura |
| Usuários | `criar_usuario`, `listar_usuarios`, `alterar_usuario`, `trocar_senha` | master |
| Equipamentos | `listar_tipos_sensor`, `ficha_do_tipo`, `listar_equipamentos`, `obter_equipamento` | leitura |
| | `criar_equipamento`, `alterar_equipamento` (inclusive desativar) | cadastro |
| Importação | `importar_caminho`, `importar_arquivos` (com `ao_progresso`), `sugerir_tipo` | cadastro |
| Envios | `listar_envios`, `obter_envio`, `resumo_leituras` | leitura |
| Qualidade | `listar_regras`, `listar_ocorrencias`, `resumo_qualidade`, `tempos_suspeitos` | leitura |
| | `configurar_regra`, `resolver_ocorrencia` | cadastro |
| Exportação | `listar_formatos_exportacao`, `exportar` | leitura |
| Plugins | `listar_plugins`, `preparar_plugin`, `instalar_plugin`, `cancelar_plugin`, `desativar_plugin`, `reativar_plugin`, `voltar_versao_plugin`, `definir_github_confiaveis`, `listar_auditoria_plugins` | master (e senha) |

Os erros são exceções de `app.nucleo.erros`, todas derivadas de `ErroServico`, e `str(erro)` já é a
mensagem para mostrar: `ErroAutenticacao`, `ErroPermissao`, `NaoEncontrado`, `Conflito`,
`ErroEnvio`, `LimiteExcedido`, `ErroRarSemFerramenta`, `EnvioRecusado` e `ErroValidacao` (com os
erros por campo). A API traduz cada uma no código HTTP correspondente (401, 403, 404, 409, 400,
413 e 422).
