# O que é o Hidrolog

O Hidrolog guarda e organiza os dados dos **sensores ambientais** do laboratório num banco de
dados único, no próprio computador. Com ele você cadastra os equipamentos, importa os arquivos
que eles gravam (por exemplo, o conteúdo de um cartão SD), confere a qualidade das leituras,
vê gráficos e tabelas e exporta os dados para análise.

Tudo roda localmente: não há servidor nem internet envolvidos no uso do dia a dia.

## As palavras que você vai ver

| Termo | O que é |
|---|---|
| **Equipamento** | Um aparelho físico instalado em algum lugar, com nome, local e tipo de sensor. |
| **Tipo de sensor** | O modelo do aparelho. Cada tipo é fornecido por um **plugin**. |
| **Plugin** | Um pacote que ensina o Hidrolog a ler os arquivos de um tipo de sensor, a mostrar os gráficos dele e a conferir a qualidade das leituras. |
| **Envio** | Uma importação: o conjunto de arquivos enviado de uma vez para um equipamento. |
| **Leitura** | Um registro do sensor num instante (uma linha de dados). |
| **Período** | O intervalo de datas que você está consultando. |
| **Ocorrência** | Um alerta, suspeita ou aviso gerado pelas regras de qualidade. |
| **Perfil** | O que cada pessoa pode fazer no app: Leitura, Cadastro ou Master. |

## Como os dados entram e saem

1. Alguém com perfil **Cadastro** cadastra o equipamento e importa os arquivos dele.
2. O plugin do tipo de sensor reconhece os arquivos, lê as leituras e o Hidrolog grava no banco,
   **sem duplicar** o que já estava lá.
3. As **regras de qualidade** do plugin conferem as leituras novas e apontam o que parece errado,
   sem nunca alterar os dados.
4. Qualquer pessoa consulta os gráficos, as tabelas e o histórico, e **exporta** o período que
   precisar.

## Por onde continuar

- [Entrar e se localizar no app](ajuda:primeiros-passos)
- [Perfis e permissões](ajuda:perfis)
- [Equipamentos e a página do equipamento](ajuda:equipamentos)
