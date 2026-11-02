# Qualidade dos dados

Cada plugin traz **regras de qualidade** para o seu tipo de sensor: por exemplo, valores fora da
faixa física possível, saltos bruscos, sensor parado ou relógio fora de ordem. As regras rodam
sozinhas a cada importação e **nunca alteram nem apagam dados**: elas só apontam o que merece
atenção.

## Ocorrências

O resultado das regras são **ocorrências**, de três níveis:

- **Alerta:** algo provavelmente errado, que pede ação (por exemplo, sensor com defeito).
- **Suspeita:** leituras que podem estar erradas. Elas aparecem destacadas nos gráficos e podem
  ser escondidas com **Ocultar suspeitas**.
- **Aviso:** informação útil, sem indicar erro.

Onde ver:

- **Início → Alertas de qualidade:** os equipamentos com ocorrências abertas.
- **Equipamentos:** a coluna Qualidade.
- **Página do equipamento → aba Qualidade:** a lista completa.

## O que o perfil Cadastro pode fazer

- **Marcar como resolvida:** depois de verificar o problema em campo ou nos dados.
- **Ajustar regra:** mudar os parâmetros de uma regra só para aquele equipamento (por exemplo,
  um limite diferente para um local mais chuvoso). Fica registrado quem alterou e quando.
