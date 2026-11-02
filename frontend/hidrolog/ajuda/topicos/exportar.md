# Exportar dados

Qualquer perfil pode exportar.

1. Abra **Exportar dados** (ou a aba **Exportar** na página do equipamento).
2. Escolha o **equipamento**, o **período** (ou "Todo o período") e o **formato**.
3. Clique em **Exportar…** e escolha onde salvar o arquivo.
4. Quando terminar, o cartão "Arquivo gerado" mostra o caminho; **Abrir pasta** abre a pasta no
   gerenciador de arquivos.

## Formatos

Os formatos dependem do plugin do tipo de sensor. Os mais comuns:

- **CSV:** uma tabela de texto, que abre em planilhas, R ou Python.
- **NetCDF:** formato científico com metadados (unidades, descrição de cada variável e a
  instituição da instalação), comum em hidrologia e meteorologia.

Se o tipo de sensor estiver sem plugin, a exportação é um **CSV genérico** com todas as colunas
guardadas no banco.

Leituras corrompidas não são exportadas. Leituras suspeitas são exportadas normalmente (as regras
de qualidade nunca apagam dados); confira a aba Qualidade se precisar filtrá-las.
