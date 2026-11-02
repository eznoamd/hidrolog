# Guia de criação de plugins de sensor

Um tipo de sensor novo é **um pacote Python novo**, sem tocar no núcleo do app. O pacote
declara tudo o que é do sensor: o manifesto, a tabela das leituras e as migrações, como ler
os arquivos (ingestão), os campos do cadastro (ficha), as regras de qualidade, as consultas,
as exportações e as abas da página do equipamento.

O modelo de referência é o plugin de exemplo **desta pasta** (`exemplos/plugin-termometro`, um
termômetro que grava um CSV com `data_hora;temperatura_c`). Copie essa pasta para um repositório
novo e troque o que for do seu sensor. O sensor de teste do núcleo
(`backend/tests/sensor_estacao`) mostra o resto do contrato: leitura paralela, nº de série lido dos
dados, ficha com migração de atributos, regras nos três níveis, dois formatos de exportação e rotas
da API.

O contrato está em `backend/hidrolog_nucleo/plugin.py` (`VERSAO_CONTRATO = "1.0"`). Um plugin
só importa de `hidrolog_nucleo.plugin` (e das próprias bibliotecas): o resto do backend
(`app`) é interno e pode mudar.

## 1. Estrutura da pasta

Cada plugin é um repositório próprio, clonado ao lado do Hidrolog (copie o
`exemplos/plugin-termometro` como ponto de partida):

```
projs/
├── hidrolog/
└── hidrolog-plugin-pluviometro/
    ├── hidrolog-plugin.toml        manifesto (lido sem executar código)
    ├── pyproject.toml          só para o caminho de desenvolvimento (pip install -e)
    └── hidrolog_pluviometro/
    ├── __init__.py             junta tudo num objeto PLUGIN
    ├── dados.py                tabela, reconhecer/ler, consultas, exportação
    ├── ficha.py                campos do cadastro
    ├── regras.py               regras de qualidade
    ├── interface.py            abas (o único módulo que importa PySide6)
    ├── migracoes/              branch Alembic do plugin
    └── amostra/                dados reais mínimos (para o kit de conformidade)
```

## 2. Manifesto (`hidrolog-plugin.toml`)

```toml
codigo = "pluviometro"                 # minúsculas, dígitos e _ ; vira o tipo de sensor e o branch Alembic
nome = "Pluviômetro de báscula"
versao = "0.1.0"                       # SemVer
contrato = "1.x"                       # versão do contrato do núcleo que o plugin usa
autor = "Laboratório X"
descricao = "Pluviômetro com datalogger: um CSV com a coluna pulsos."
icone = "cloud-rain"                   # um ícone Lucide de design/assets/icones
modulo = "hidrolog_pluviometro"        # pacote Python com o objeto PLUGIN
requer = []                            # dependências compiladas que o app precisa ter (numpy, netCDF4...)
tabelas = ["pluviometro_leitura"]      # só para mostrar na confirmação da instalação
cadastro = ["Resolução da báscula", "Área de captação"]   # idem
```

O gerenciador de plugins lê esse arquivo **sem importar o código**: com ele mostra o que vai
entrar e recusa o pacote se o contrato não for compatível, se o código já pertencer a outro
plugin ou se faltar uma dependência de `requer`. Dependências em Python puro podem vir junto,
dentro do pacote.

## 3. Tabela e migração

As leituras ficam numa tabela do plugin, sobre a `Base` do núcleo, com `equipamento_id` e
`envio_id` e uma chave natural única (o núcleo deduplica por ela):

```python
from hidrolog_nucleo.plugin import Base

class PluvioLeitura(Base):
    __tablename__ = "pluviometro_leitura"
    __table_args__ = (UniqueConstraint("equipamento_id", "tempo"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"))
    envio_id: Mapped[int] = mapped_column(ForeignKey("envio.id"), index=True)
    tempo: Mapped[datetime] = mapped_column(DateTime)
    pulsos: Mapped[int] = mapped_column(Integer)
```

A migração fica em `migracoes/`, como um branch do Alembic com o código do plugin, e depende
da revisão do núcleo de que precisa (veja `hidrolog_termometro/migracoes/` no plugin de exemplo):

```python
revision = "pluviometro_0001"
down_revision = None
branch_labels = ("pluviometro",)
depends_on = "nucleo_0001"
```

Com o plugin instalado em desenvolvimento, `backend/venv/bin/python -m app nova-migracao
--sensor pluviometro -m "inicial"` gera a migração a partir do modelo. Ao abrir, o app sobe as
migrações do plugin, **com backup do banco antes** se o banco já existia.

## 4. Ingestão em três camadas

```
1. Núcleo — ABRIR        zip / rar / pasta / arquivos soltos (+ zip dentro de zip, até 2 níveis)
                         -> ArvoreArquivos: nomes e tamanhos, sem ler conteúdo
2. Plugin — RECONHECER   reconhecer(arvore, verificar=False) -> PlanoImportacao ou Recusa
3. Plugin — LER          ler(unidade) -> uma leitura (dict) por vez, em fluxo
   Núcleo — GRAVAR       lotes numa transação, deduplicação pela chave, progresso,
                         cancelamento, paralelismo, regras de qualidade, registro do envio
```

```python
from hidrolog_nucleo.plugin import PlanoImportacao, Recusa, Unidade

def reconhecer(arvore, verificar=False):
    csvs = arvore.com_extensao(".csv")
    if not csvs:
        return Recusa("nenhum .csv do datalogger encontrado")
    unidades = []
    for a in csvs:
        if "pulsos" not in a.primeira_linha().lower():
            return Recusa(f"{a.nome}: falta a coluna 'pulsos'")
        unidades.append(Unidade(a.nome, arquivos=[a]))
    outros = [a for a in arvore if a not in csvs]
    return PlanoImportacao(unidades, ignorados=[(a, "não é .csv") for a in outros])

def ler(unidade):
    for linha in unidade.arquivo.linhas_csv():
        yield {"tempo": datetime.fromisoformat(linha["data_hora"]), "pulsos": int(linha["pulsos"])}
```

- **`ArquivoArvore`**: `caminho`, `nome`, `pasta`, `extensao`, `tamanho`; `ler()` (o conteúdo
  inteiro, com limite por arquivo), `texto()`, `abrir()` (fluxo binário), `linhas()`,
  `primeira_linha()` e `linhas_csv()` (em fluxo, sem limite por arquivo; todos contam no
  limite total do envio).
- **`ArvoreArquivos`**: iterável; `com_extensao(".csv")`, `procurar("calibracao.json")`, `pastas()`.
- **`PlanoImportacao`**: `unidades` (um arquivo, um grupo, um trecho; `Unidade.dados` leva o
  que o reconhecer já descobriu, ex. uma calibração), `ignorados` (arquivo, motivo),
  `metadados` (`"numero_serie"` é conferido com o cadastro e vira aviso se for outro
  equipamento) e `avisos`.
- **`Recusa(motivo)`**: o envio não tem a estrutura esperada; o usuário vê o motivo e nada é
  gravado. Uma árvore vazia ou de outro sensor **precisa** ser recusada (o kit confere).
- `verificar=True`: o núcleo pergunta "isto é seu?" para sugerir o tipo de sensor; olhe só a
  estrutura, sem ler conteúdo pesado.
- Uma unidade que levanta exceção vira um aviso e conta como ignorada; o envio continua.

No `__init__.py`:

```python
Ingestao(tabela=PluvioLeitura, reconhecer=reconhecer, ler=ler,
         chave=("equipamento_id", "tempo"), coluna_tempo="tempo",
         coluna_corrompido=None,        # coluna booleana de leitura corrompida (guardada para diagnóstico)
         coluna_numero_serie=None,      # coluna conferida com o número de série do cadastro
         leitura_paralela=False)        # True: as unidades são lidas em processos (ler tem de ser de módulo)
```

Exemplos de formatos que o mesmo núcleo já lê nos testes (`backend/tests/plugins_teste/`): um
CSV de 20 mil linhas lido em fluxo e um sensor com `.bin` + `calibracao.json` dentro de um zip
dentro de outro.

## 5. Ficha (cadastro do equipamento)

O núcleo já tem nome, número de série, local, coordenadas, altitude, data de instalação,
situação e observações. O plugin acrescenta os campos do tipo; a tela de cadastro é gerada da
ficha e a validação é do backend:

```python
from hidrolog_nucleo.plugin import Campo

FICHA = (
    Campo("resolucao_mm", "Resolução da báscula", tipo="decimal", unidade="mm/pulso", padrao=0.2,
          minimo=0.01, maximo=5),
    Campo("area_cm2", "Área de captação", tipo="decimal", unidade="cm²"),
    Campo("firmware", "Firmware do datalogger", somente_leitura=True, origem="leituras", coluna="firmware"),
)
```

Tipos: `texto`, `inteiro`, `decimal`, `booleano`, `data`, `escolha` (com `opcoes`). Campos com
`origem="leituras"` são preenchidos pelo núcleo depois de cada importação (o valor mais
recente da `coluna`, ou o metadado do plano com a mesma chave). Os valores ficam em
`equipamento.atributos` (JSON), com `versao_ficha`. Se a ficha mudar, aumente
`Plugin.versao_ficha` e dê uma `migrar_atributos(atributos, versao_antiga) -> dict`.

## 6. Regras de qualidade

Regras **nunca alteram dados**: produzem ocorrências ligadas à leitura, ao envio ou ao
equipamento (o núcleo roda as regras-função num savepoint desfeito no fim).

```python
from hidrolog_nucleo.plugin import Ocorrencia, Regra

def sem_dados(ctx):                        # nível equipamento: ctx.sessao, ctx.agora, ctx.parametros
    ultima = ctx.sessao.scalar(select(func.max(PluvioLeitura.tempo))
                               .where(PluvioLeitura.equipamento_id == ctx.equipamento.id))
    if ultima and ctx.agora - ultima > timedelta(days=ctx.parametros["dias"]):
        return [Ocorrencia(f"sem dados desde {ultima:%d/%m/%Y}", ultima)]
    return []

REGRAS = (
    # declarativa: uma ocorrência por leitura em que "coluna operador limite"
    Regra("intensidade_impossivel", "Intensidade acima do limite", nivel="leitura", severidade="suspeita",
          parametros={"limite_mm_h": 300}, coluna="intensidade", operador=">", limite="limite_mm_h",
          mensagem="{valor:.0f} mm/h acima de {limite_mm_h} mm/h"),
    # por função
    Regra("sem_dados", "Sem dados há muitos dias", nivel="equipamento", severidade="alerta",
          parametros={"dias": 7}, funcao=sem_dados, ajuda_parametros={"dias": "dias sem leitura"}),
)
```

- Níveis: `leitura` (na importação, a cada lote de leituras novas, em `ctx.linhas`), `envio`
  (no fim de cada importação, com `ctx.inicio`/`ctx.fim` e `ctx.envio`) e `equipamento` (ao
  abrir o app e depois de cada envio; fica uma ocorrência aberta enquanto a condição vale).
- Severidades: `aviso`, `suspeita` (as leituras aparecem com destaque nos gráficos e saem com
  "ocultar suspeitas"; as exportações levam a coluna `qualidade`) e `alerta`.
- Os parâmetros têm padrão e podem ser ajustados por equipamento (perfil cadastro ou superior)
  na aba Qualidade; quem alterou fica registrado.

## 7. Consultas e exportação

As consultas são funções de um módulo do plugin (`Plugin.consultas`), com o mesmo contrato do
serviço do núcleo: recebem o `Usuario` e conferem o perfil.

```python
from hidrolog_nucleo.plugin import obter_equipamento_orm, sessao_autorizada

def buscar(usuario, equipamento_id, inicio=None, fim=None):
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        obter_equipamento_orm(sessao, equipamento_id, "pluviometro")
        ...
```

A exportação declara os formatos e escreve o arquivo em blocos; o núcleo cuida do nome
temporário e passa um `ContextoExportacao` com `qualidade(tempo)` (códigos das regras que
marcaram a leitura) para a coluna de qualidade:

```python
FORMATOS = (FormatoExportacao("csv", "CSV (tempo, pulsos, qualidade)", ".csv", "text/csv"),)

def exportar(sessao, equipamento_id, inicio, fim, formato, destino, contexto): ...
Exportacao(formatos=FORMATOS, exportar=exportar)
```

Sem o plugin carregado, os dados continuam acessíveis pela exportação genérica do núcleo.

## 8. Interface (abas)

O módulo `Plugin.interface` tem a lista `ABAS`. Cada aba recebe o `ContextoAba` pronto
(`equipamento`, `inicio`/`fim`, `usuario`, `consultas`, `ocultar_suspeitas`, `suspeitas()`,
`executar(...)` para rodar numa thread, `tratar_erro(...)`, `sessao.extras` para cache) e
**não tem seletor de equipamento nem de período**. Quando o período, o filtro ou os dados
mudam, o núcleo chama `atualizar(contexto)` no widget da aba.

```python
from hidrolog_nucleo.plugin import Aba

def _criar_acumulada(contexto):
    from .abas import AbaAcumulada          # só aqui importa PySide6/matplotlib
    return AbaAcumulada(contexto)

ABAS = [Aba("acumulada", "Chuva acumulada", _criar_acumulada, icone="chart-line",
            descricao="Chuva acumulada no período.")]
```

Use os componentes do design (`design.componentes`: `CartaoMetrica`, `TabelaFiltravel`,
`FiguraIncorporada`, `EstadoVazio`, `FaixaAviso`, `formatos`) e os tokens (`design.tema`),
sem cor ou tamanho solto. O núcleo acrescenta as abas comuns: Qualidade, Envios, Importar,
Exportar e Cadastro. Um plugin sem `interface` fica só com elas.

## 9. Montagem do objeto `PLUGIN` (`__init__.py`)

```python
PLUGIN = Plugin(
    manifesto=carregar_manifesto(__file__),
    modelos=(PluvioLeitura,),
    migracoes=Path(__file__).parent / "migracoes",
    ingestao=Ingestao(tabela=PluvioLeitura, reconhecer=reconhecer, ler=ler),
    ficha=FICHA,
    regras=REGRAS,
    consultas="hidrolog_pluviometro.dados",
    exportacao=Exportacao(formatos=FORMATOS, exportar=exportar),
    interface="hidrolog_pluviometro.interface",
    amostra=Path(__file__).parent / "amostra",
)
```

O `__init__` não pode importar PySide6: o backend, o comando de linha e os testes sem tela
importam o plugin sem a interface.

## 10. Testes com o kit de conformidade

Coloque em `amostra/` um pouco de dados **reais** do sensor e rode, de dentro da pasta do plugin:

```bash
cd hidrolog-plugin-pluviometro
../hidrolog/frontend/venv/bin/python -m pytest --plugin=pluviometro   # com a interface (offscreen)
../hidrolog/backend/venv/bin/python -m pytest --plugin=pluviometro    # sem Qt: a aba é pulada
```

O kit confere: manifesto válido e igual ao do `PLUGIN`; contrato compatível; o pacote carrega
sem PySide6; migrações que sobem e descem num banco vazio; importação da amostra;
reimportação sem duplicar; `reconhecer` aceitando a amostra e **recusando** uma árvore vazia e
uma de outro sensor; a ficha aceitando os padrões e recusando valores inválidos; as regras sem
erro em dados vazios e com a amostra; as exportações reabrindo (com a coluna de qualidade); e
cada aba abrindo sem dados e com dados. O plugin é achado pelo entry point ou, se não estiver
instalado, pela pasta atual (ou `--plugin-pasta`).

## 11. Instalação

| Caminho | Como | Para quem |
|---|---|---|
| Gerenciador de plugins | Configurações → Plugins → Importar plugin → pasta, `.zip` ou GitHub (URL + tag); confirmação + senha do master; reiniciar o Hidrolog | uso no laboratório (inclusive no executável) |
| Desenvolvimento | `pyproject.toml` com `[project.entry-points."hidrolog.plugins"] pluviometro = "hidrolog_pluviometro:PLUGIN"` e `venv/bin/pip install -e ../../hidrolog-plugin-pluviometro` (em `hidrolog/backend` e `hidrolog/frontend`); reiniciar | quem está programando o plugin |

Pelo gerenciador, o pacote vai para `<dados do app>/plugins/<codigo>/<versao>/` (a versão
anterior fica guardada para voltar), com origem e SHA-256 registrados e auditados. Do GitHub,
informe sempre a **tag ou release**: o app baixa
`https://github.com/<dono>/<repo>/archive/refs/tags/<tag>.zip`, então o que está instalado
não muda sozinho. Se o mesmo código vier das duas fontes, vale o de desenvolvimento e a tela
Plugins mostra o conflito.

## 12. Uso

Equipamentos → Novo equipamento → tipo do seu sensor: o formulário já traz os campos da
ficha. Importe a amostra pela aba Importar do equipamento (ou pela página Importar dados) e
abra a página do equipamento: as abas do plugin aparecem junto com as comuns.
