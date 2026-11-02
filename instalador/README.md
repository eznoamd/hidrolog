# instalador

Esta pasta transforma o Hidrolog num programa de Windows comum: um `Hidrolog-Setup-<versão>.exe`
que a pessoa baixa, executa e segue as telas, sem instalar Python nem abrir um terminal. O
instalador coloca o app no computador, cria o atalho no menu Iniciar, cria o usuário master e,
se desejado, grava a identidade do laboratório (nomes e logos). O resultado é gerado
automaticamente pelo GitHub Actions, numa máquina Windows, a cada versão publicada.

## Estrutura

```
instalador/
├── entrada.py      o ponto de entrada do Hidrolog.exe
├── hidrolog.spec   a receita do PyInstaller (o que entra no executável)
└── hidrolog.iss    o script do Inno Setup (as telas e os passos da instalação)
```

O workflow que junta tudo fica em `../.github/workflows/instalador-windows.yml`. As pastas
`build/` e `dist/`, criadas durante a geração, não são versionadas.

## Funcionamento

### O executável

O **PyInstaller** junta numa pasta o Python, o Qt, as bibliotecas e o código do Hidrolog, com um
`Hidrolog.exe` que roda sem nada instalado no computador. O `hidrolog.spec` diz o que entra além do
que o código importa diretamente: as migrações do banco (lidas como arquivos pelo Alembic), as
fontes, os ícones e os estilos dos gráficos do design, os tópicos da Central de ajuda e um
conjunto amplo da biblioteca padrão do Python. Esse último ponto existe por causa dos plugins:
eles são instalados depois, pelo gerenciador, e podem usar módulos que o app em si nunca importa.

O `entrada.py` faz o mesmo executável servir a três usos. Sem argumentos, abre o app. Com
`admin`, vira a linha de comando do backend (`Hidrolog.exe admin criar-master ...`,
`Hidrolog.exe admin redefinir-senha ...`), ligando-se ao console de quem o chamou para mostrar a
saída e pedir a senha. Com `--autoteste`, abre um banco temporário, aplica o tema, carrega a
ajuda, monta a janela sem mostrá-la e, com `--plugin PASTA`, instala um plugin e importa e
exporta a amostra dele, devolvendo erro se algo faltar no pacote. No app empacotado, a importação
usa um processo só por padrão (a variável `HIDROLOG_PROCESSOS` muda isso).

### O instalador

O **Inno Setup** empacota a pasta do PyInstaller num único instalador, em português. Ele instala
só para o usuário atual, em `%LOCALAPPDATA%\Programs\Hidrolog`, sem pedir permissão de
administrador, porque o banco do Hidrolog fica na pasta de dados desse mesmo usuário
(`%LOCALAPPDATA%\Hidrolog`). As telas próprias do Hidrolog são duas. A primeira pede o login, o
nome e a senha do **master**; ao terminar, o instalador grava a senha num arquivo temporário e
roda `Hidrolog.exe admin criar-master --senha-arquivo ...`, para que ela nunca apareça numa
linha de comando, e apaga o arquivo em seguida. A segunda, opcional, pede a sigla e o nome do
laboratório e da instituição e as duas logos, e grava a pasta de marca (`marca.toml` e as imagens).

Numa atualização, as duas telas não aparecem: se já existe um banco, o master já existe; se já
existe uma marca, ela não é sobrescrita. Desinstalar remove o programa, mas mantém a pasta de
dados com o banco, os plugins e a marca. Numa instalação silenciosa (`/VERYSILENT`), o master não
é criado, e o app abre na tela que mostra o comando para criá-lo.

### A geração no GitHub Actions

O PyInstaller não gera executáveis de Windows a partir de outro sistema, então o instalador é
feito numa máquina Windows do GitHub. O workflow instala o Hidrolog e o PyInstaller, gera o
executável, roda o autoteste completo nele (com o plugin de exemplo), confere a criação do master
pela linha de comando, compila o instalador, instala-o em modo silencioso numa pasta de teste e
roda o autoteste de novo no app instalado. Só então guarda o `Hidrolog-Setup-<versão>.exe` como
artefato e, quando a execução veio de uma tag `v*`, publica-o na release dessa versão. Um segundo
job roda os testes do projeto no Windows, de forma informativa, sem bloquear o instalador.

## Integração com o sistema

O instalador não muda nada no funcionamento do Hidrolog: ele usa a mesma pasta de dados, a mesma
pasta de marca e o mesmo gerenciador de plugins da versão de desenvolvimento. O código do app só
sabe que está empacotado em dois pontos: o padrão de um processo na importação e a tela "falta
criar o master", que passa a mostrar o comando do `Hidrolog.exe` em vez do comando do Python.

Os plugins continuam entrando pelo gerenciador do app, a partir de uma pasta ou de um `.zip`. No
app instalado, um plugin conta com a biblioteca padrão do Python, com o numpy, o matplotlib, o
netCDF4, o SQLAlchemy, o PySide6 e o `design`; uma dependência em Python puro que não esteja nessa
lista precisa vir dentro do próprio plugin.

## Execução e testes

Para gerar uma versão: publique uma tag (`v0.2.0`, por exemplo) ou rode o workflow à mão em
Actions → Instalador Windows → Run workflow; o instalador fica nos artefatos da execução e, nas
tags, na página de releases.

Para gerar à mão num Windows, com Python 3.12 e o Inno Setup 6 instalados:

```powershell
python -m pip install .\backend .\design .\frontend pyinstaller
cd instalador
pyinstaller --noconfirm hidrolog.spec
dist\Hidrolog\Hidrolog.exe --autoteste autoteste.txt ; type autoteste.txt
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DVersao=0.1.0 hidrolog.iss
```

O mesmo `hidrolog.spec` também funciona no Linux (gera um executável de Linux), o que serve para
conferir a receita sem uma máquina Windows.
