# Equipamentos e a página do equipamento

## A lista de equipamentos

A página **Equipamentos** mostra os aparelhos ativos, com tipo, local e a situação da qualidade.
Marque **Mostrar desativados** para ver também os desativados. Use a busca no alto da tabela para filtrar. Para abrir um equipamento, clique duas
vezes na linha ou selecione e clique em **Abrir**.

## Cadastrar um equipamento (perfil Cadastro)

1. Clique em **Novo equipamento**.
2. Escolha o **tipo de sensor**. Só aparecem os tipos com plugin instalado.
3. Preencha o formulário. Do lado esquerdo ficam os dados comuns (nome, local, posição no mapa);
   do lado direito, a **ficha** do tipo de sensor, com os campos que o plugin pede.
4. Clique em **Salvar**. Se algum campo estiver errado, a mensagem aparece logo abaixo dele.

A posição é escolhida **clicando no mapa**, sem digitar coordenadas. Dados que o próprio sensor
informa nos arquivos (por exemplo, número de série ou versão do firmware) **não** são digitados:
eles aparecem sozinhos depois da primeira importação, no cartão "Informado pelo sensor".

## Desativar um equipamento (perfil Cadastro)

Quando um aparelho sai de uso, selecione-o na lista (ou abra a aba **Cadastro** dele) e clique em
**Desativar**. Ele sai da lista de equipamentos e da importação, mas **nada é apagado**: as
leituras, os envios e o histórico continuam no banco, e os dados podem ser exportados. Para
trazê-lo de volta, marque **Mostrar desativados**, selecione-o e clique em **Reativar**.

## A página do equipamento

No alto ficam o nome, o tipo, o local, o selo de qualidade e o **período**. Escolha o período
uma vez e todas as abas passam a mostrar esse intervalo. "Todo o período" mostra tudo o que há
no banco. A opção **Ocultar suspeitas** tira dos gráficos as leituras marcadas como suspeitas
pelas regras de qualidade.

As abas são de dois tipos:

- **Abas do tipo de sensor:** gráficos e tabelas próprios daquele aparelho, fornecidos pelo
  plugin. Os gráficos acompanham o tema claro/escuro. Role a página normalmente com o mouse,
  mesmo por cima de um gráfico.
- **Abas comuns**, iguais para todos os equipamentos:
  - **Qualidade:** ocorrências e regras (veja [Qualidade dos dados](ajuda:qualidade)).
  - **Envios:** as importações deste equipamento.
  - **Importar:** importar direto para este equipamento (perfil Cadastro).
  - **Exportar:** exportar o período escolhido.
  - **Cadastro:** os dados cadastrados e os informados pelo sensor; **Editar** e **Desativar**
    (perfil Cadastro).

Se o plugin de um tipo de sensor for desativado ou removido, os equipamentos e os dados continuam
no banco. A página do equipamento mostra só as abas comuns, com um aviso, e a exportação passa a
ser um CSV genérico com todas as colunas. **Não é possível importar** dados novos para ele, porque
é o plugin que sabe ler os arquivos: a aba Importar some e ele sai da página Importar dados até o
plugin voltar.

## Recentes

Os últimos equipamentos que você abriu aparecem em **Recentes**, na barra lateral. A lista é de
cada usuário.
