# Perfis e permissões

Cada pessoa tem o **próprio usuário** e um perfil. Não compartilhe senhas: o histórico registra
quem fez cada envio.

| O que | Leitura | Cadastro | Master |
|---|:-:|:-:|:-:|
| Início, Histórico, Exportar e a página de cada equipamento | ✓ | ✓ | ✓ |
| Consultar equipamentos | ✓ | ✓ | ✓ |
| Cadastrar e editar equipamentos | | ✓ | ✓ |
| Importar dados | | ✓ | ✓ |
| Ajustar regras de qualidade e marcar ocorrências como resolvidas | | ✓ | ✓ |
| Usuários e Configurações (plugins e auditoria) | | | ✓ |
| Minha conta (nome, senha, tema) | ✓ | ✓ | ✓ |

- **Leitura:** consulta e exporta; não altera nada no banco.
- **Cadastro:** o perfil do dia a dia de quem cuida dos equipamentos e dos dados.
- **Master:** administra o app. Também faz tudo o que o Cadastro faz.

O app esconde o que o seu perfil não permite. Mesmo que alguém tente por outro caminho, cada
operação é conferida de novo antes de gravar, e o app responde com uma mensagem clara.

O perfil é dado pelo master na página Usuários. O perfil **master** não é dado nem retirado pelo
app: ele é criado por um comando, na instalação (veja [Usuários](ajuda:usuarios)).
