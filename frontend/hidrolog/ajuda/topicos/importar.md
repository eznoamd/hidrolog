# Importar dados

Perfil necessário: **Cadastro** ou **Master**.

## Passo a passo

1. Abra **Importar dados** (ou a aba **Importar** na página do equipamento).
2. Escolha o **equipamento** que gravou os dados. Só aparecem os equipamentos ativos cujo tipo
   de sensor tem o plugin carregado.
3. Arraste para a área tracejada, ou clique em **Escolher…**, o que você tem:
   - a **pasta** copiada do cartão SD (ou uma subpasta dela);
   - um arquivo **.zip** ou **.rar** com os dados;
   - outros formatos que o plugin do tipo de sensor aceite.

   O mesmo botão aceita **pasta ou arquivo**: no diálogo, selecione um arquivo e clique em
   *Escolher*, ou entre na pasta desejada e clique em *Escolher* sem selecionar nada.
4. Clique em **Importar**. A barra mostra as etapas: examinando os arquivos, interpretando e
   gravando.
5. No fim aparece o **resumo**: leituras novas, duplicadas, corrompidas, arquivos ignorados,
   período coberto e avisos.

Se os arquivos parecerem de outro tipo de sensor, o app avisa antes de você importar. Confira se
escolheu o equipamento certo.

## Pode importar de novo sem medo

O Hidrolog **não duplica** leituras. Reenviar o mesmo cartão (ou um cartão com dados novos e
antigos misturados) grava só o que é novo; o resto aparece como "duplicadas" no resumo.

## Cancelar

Clique em **Cancelar** durante a importação. **Nada é gravado**: o envio é desfeito por inteiro.

## Leituras corrompidas e arquivos ignorados

- **Corrompidas:** registros que o plugin não conseguiu interpretar. Eles ficam guardados só para
  diagnóstico e não entram nos gráficos nem na exportação.
- **Ignorados:** arquivos que não são dados do sensor (por exemplo, arquivos do sistema). A lista
  aparece no detalhe do envio.

## Arquivos .rar

Arquivos `.rar` comprimidos precisam de um programa extra no computador (no Linux, `unar`). Se ele
faltar, o app diz exatamente isso. Uma alternativa é descompactar o `.rar` e importar a pasta.

Depois de importar, veja o envio no [Histórico de envios](ajuda:historico) e os dados na
[página do equipamento](ajuda:equipamentos).
