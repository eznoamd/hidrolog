# Plugins de sensor

Só o **master** vê esta parte (Configurações → Plugins).

## O que é um plugin

Cada **tipo de sensor** é um plugin: um pacote que diz ao Hidrolog como reconhecer e ler os
arquivos do aparelho, onde guardar as leituras, que campos pedir no cadastro, quais regras de
qualidade aplicar, que formatos exportar e quais abas mostrar na página do equipamento.

O Hidrolog **não vem com nenhum plugin de sensor**: cada laboratório instala os que usa.

**Atenção: um plugin é um programa.** Ele roda com o mesmo acesso do Hidrolog ao computador e ao
banco. Instale só plugins de origem confiável.

## A lista

A tabela mostra cada plugin com versão, origem e situação: ativo, desativado, incompatível (com
o motivo), em conflito, ou instalado aguardando reinício.

## Importar (instalar ou atualizar) um plugin

1. Clique em **Importar plugin** e escolha a origem:
   - **Do computador (pasta ou .zip):** a pasta do plugin ou o pacote `.zip`;
   - **Repositório do GitHub:** endereço e versão (tag).
2. O app **prepara** o plugin (copia e confere, **sem executar nada dele**). Um indicador aparece
   sobre a lista enquanto isso.
3. Confira a **confirmação**: nome, versão, origem, autor, contrato, a impressão digital
   (SHA-256), as tabelas que serão criadas e os campos que entram no cadastro.
4. Digite a **senha do master** para confirmar. Três senhas erradas cancelam.
5. **Reinicie o Hidrolog.** Toda mudança de plugin vale só na próxima abertura. Ao abrir, o app
   cria as tabelas do plugin e faz **uma cópia de segurança do banco antes**.

Um plugin é recusado se o contrato não for compatível com esta versão do Hidrolog, se o código
dele já pertencer a outro plugin ou se faltar alguma dependência.

## Desativar, reativar e voltar versão

- **Desativar:** o tipo de sensor some das telas de cadastro e importação, e não é mais possível
  importar dados para os equipamentos dele; os equipamentos e os dados **continuam no banco**
  (consulta e exportação genérica). **Reativar** traz tudo de volta.
- **Voltar versão:** volta para uma versão instalada antes (o app guarda as versões anteriores).

As três ações pedem a senha do master e valem ao reiniciar.

## Repositórios confiáveis e auditoria

- **Repositórios confiáveis do GitHub:** se a lista tiver algum endereço, o app só aceita
  plugins do GitHub vindos desses repositórios e recusa os outros. Com a lista vazia, qualquer
  repositório é aceito (sempre com a confirmação e a senha). Salvar a lista pede a senha do master.
- **Auditoria:** tudo o que foi feito com plugins (quem, quando, o quê, resultado), inclusive as
  tentativas recusadas.

Para quem vai escrever um plugin, veja [Criar um plugin](ajuda:criar-plugin).
