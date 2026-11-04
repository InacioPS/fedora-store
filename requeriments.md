# Requisitos — Loja de aplicativos para Fedora com WM

## 1. Visão do projeto

Desenvolver uma loja gráfica para Fedora, voltada a usuários que utilizam window managers (WM) e preferem instalar programas por pacotes RPM e repositórios.

A aplicação terá uma interface convencional de loja, com busca, categorias, páginas de detalhes, atualizações e gerenciamento de pacotes. Será desenvolvida com GTK4 e libadwaita.

A loja deverá integrar o DNF, o Terra e projetos COPR, deixando sempre clara a origem dos pacotes e as mudanças que serão aplicadas ao sistema.

## 2. Objetivos

- Facilitar a descoberta e instalação de aplicativos.
- Permitir instalar, remover e atualizar pacotes.
- Permitir instalar ou remover vários pacotes em uma operação.
- Oferecer uma área para explorar pacotes do Terra.
- Oferecer uma área para explorar projetos e pacotes do COPR.
- Tornar visíveis a origem, a versão e as mudanças envolvidas em cada operação.
- Funcionar em sessões com window managers, sem depender de um desktop GNOME completo.

## 3. Requisitos funcionais

| ID | Requisito | Prioridade |
|---|---|---|
| RF01 | Exibir uma página inicial com aplicativos em destaque, categorias e atualizações disponíveis. | MVP |
| RF02 | Permitir pesquisar pacotes por nome, descrição e categoria. | MVP |
| RF03 | Mostrar detalhes do pacote: nome, descrição, versão, tamanho, origem e estado de instalação. | MVP |
| RF04 | Permitir instalar pacotes. | MVP |
| RF05 | Permitir remover pacotes. | MVP |
| RF06 | Permitir selecionar vários pacotes e instalá-los ou removê-los em lote. | MVP |
| RF07 | Antes de aplicar uma operação, exibir um resumo dos pacotes afetados, dependências, remoções e espaço estimado. | MVP |
| RF08 | Exibir o progresso e o resultado das operações. | MVP |
| RF09 | Permitir cancelar operações quando o backend oferecer suporte ao cancelamento seguro. | Desejável |
| RF10 | Listar atualizações disponíveis. | MVP |
| RF11 | Permitir atualizar pacotes selecionados ou todos os pacotes atualizáveis. | MVP |
| RF12 | Listar repositórios configurados e indicar quais estão habilitados. | MVP |
| RF13 | Permitir adicionar, habilitar, desabilitar e remover repositórios, com confirmação. | MVP |
| RF14 | Disponibilizar uma área dedicada ao Terra, com seus pacotes identificados pela origem. | MVP |
| RF15 | Disponibilizar uma área para pesquisar projetos COPR. | MVP |
| RF16 | Mostrar o mantenedor, o nome do projeto e a descrição de cada projeto COPR. | MVP |
| RF17 | Mostrar os pacotes publicados por um projeto COPR. | MVP |
| RF18 | Pedir confirmação antes de habilitar um projeto COPR ou instalar pacotes dele. | MVP |
| RF19 | Identificar a origem do pacote — Fedora, Terra, COPR ou outro repositório — nos resultados, nos detalhes e na confirmação da operação. | MVP |
| RF20 | Mostrar o histórico de operações e os pacotes alterados em cada transação. | Desejável |
| RF21 | Avisar quando uma operação for substituir pacotes, remover dependências ou causar alterações relevantes. | Desejável |
| RF22 | Permitir atualizar os metadados dos repositórios e informar falhas de conexão ou metadados desatualizados. | Desejável |
| RF23 | Oferecer filtros para pacotes instalados, disponíveis e atualizáveis. | Desejável |

## 4. Requisitos para Terra e COPR

### 4.1 Terra

- Apresentar o Terra como uma origem de pacotes identificável.
- Permitir explorar os pacotes disponíveis no repositório.
- Mostrar quando um pacote selecionado será obtido do Terra.
- Não ocultar a origem quando mais de um repositório oferecer pacotes com o mesmo nome.
- Informar quando o repositório estiver desabilitado ou seus metadados estiverem indisponíveis.

### 4.2 COPR

- Apresentar projetos COPR separadamente dos repositórios oficiais do Fedora.
- Mostrar o nome do projeto, mantenedor, descrição e pacotes publicados.
- Indicar claramente que se trata de um projeto comunitário.
- Exigir confirmação antes de habilitar um projeto ou instalar pacotes dele.
- Informar quais repositórios serão habilitados.
- Permitir desabilitar ou remover a configuração de um projeto COPR.
- Não apresentar projetos COPR como se fossem fontes oficiais do Fedora.

## 5. Requisitos não funcionais

| ID | Requisito | Critério |
|---|---|---|
| RNF01 | Segurança | A interface não deve rodar como administrador. Operações privilegiadas devem passar por um mecanismo apropriado de autorização do sistema, como Polkit. |
| RNF02 | Integridade das operações | A aplicação deve apresentar o plano de alterações antes de aplicar uma transação. |
| RNF03 | Transparência | Origem e versão do pacote devem aparecer nos resultados, detalhes e resumos das operações. |
| RNF04 | Compatibilidade com WM | A aplicação deve funcionar em sessões com window managers, sem exigir componentes exclusivos do GNOME Shell. |
| RNF05 | Integração visual | A interface deve usar GTK4 e libadwaita e funcionar em sistemas com as dependências necessárias instaladas. |
| RNF06 | Desempenho | Buscas, atualização de metadados e operações demoradas não devem congelar a interface. |
| RNF07 | Resiliência | A aplicação deve tratar falhas de rede, repositórios indisponíveis, conflitos e cancelamentos sem deixar a interface em estado inconsistente. |
| RNF08 | Acessibilidade | A interface deve considerar leitores de tela, contraste, escala de texto e navegação por teclado, mesmo que o teclado não seja o foco principal do produto. |
| RNF09 | Manutenção | A interface, a lógica da loja e o backend de pacotes devem ser separados para facilitar manutenção e substituição do backend. |
| RNF10 | Privacidade | Não deve haver telemetria ou envio de histórico de uso por padrão. |
| RNF11 | Internacionalização | Os textos devem ser preparados para tradução desde o início. |
| RNF12 | Testabilidade | Deve ser possível testar a interface e os fluxos com um backend simulado, sem modificar o sistema do desenvolvedor. |

## 6. Proposta de interface

A navegação principal pode incluir:

- **Início:** destaques, categorias e atualizações.
- **Explorar:** busca e navegação por categorias.
- **Instalados:** programas instalados e opções de remoção.
- **Atualizações:** lista de pacotes atualizáveis.
- **Fontes:** repositórios configurados, Terra e projetos COPR.
- **Histórico:** operações realizadas anteriormente.

### Página de detalhes do pacote

Deve apresentar:

- Nome e descrição.
- Ícone, quando disponível.
- Versão disponível e versão instalada, se aplicável.
- Origem do pacote.
- Tamanho do download e espaço estimado, quando disponíveis.
- Botão de instalar, remover ou atualizar.
- Avisos sobre dependências ou mudanças relevantes.

### Revisão da operação

Antes de executar uma transação, apresentar:

- Pacotes que serão instalados.
- Pacotes que serão atualizados.
- Pacotes que serão removidos.
- Dependências adicionadas ou removidas.
- Origem dos pacotes.
- Espaço estimado, quando disponível.
- Botões para confirmar ou cancelar.

## 7. Arquitetura inicial

### 7.1 Interface

- GTK4 e libadwaita.
- Páginas de início, busca, detalhes, instalados, atualizações, fontes e histórico.
- Componentes de interface desacoplados da implementação do gerenciador de pacotes.

### 7.2 Catálogo

- Pesquisa de pacotes.
- Exibição de metadados, categorias e origens.
- Tratamento de metadados ausentes ou incompletos.

### 7.3 Backend de pacotes

- Consultas de pacotes e repositórios.
- Resolução e apresentação das transações.
- Instalação, remoção e atualização.
- Autorização para operações privilegiadas.

Para Fedora com DNF5, avaliar a integração com o `dnf5daemon` e suas APIs. A aplicação deve rodar como usuário normal e solicitar autorização somente quando precisar aplicar mudanças no sistema.

### 7.4 Gerenciador de fontes

- Listagem e configuração de repositórios.
- Tratamento separado para Fedora, Terra e COPR.
- Confirmação explícita antes de habilitar uma fonte comunitária.
- Identificação da origem dos pacotes.

## 8. Cuidados de implementação

- Evitar executar comandos `sudo dnf` montados diretamente pela aplicação.
- Não instalar ou habilitar fontes sem apresentar previamente o que será alterado.
- Não esconder conflitos, remoções ou substituições propostos pelo DNF.
- Não tratar pacotes do COPR como equivalentes a pacotes oficiais do Fedora.
- Considerar que descrições, ícones e categorias podem estar ausentes em alguns pacotes.
- Planejar desde o início o suporte às versões do Fedora pretendidas, pois a integração com o DNF pode variar conforme a versão.

## 9. Escopo recomendado para o MVP

1. Busca e navegação por pacotes.
2. Página de detalhes com versão e origem.
3. Instalação e remoção de pacotes.
4. Operações em lote.
5. Atualização de pacotes.
6. Revisão da transação antes de aplicá-la.
7. Listagem básica de repositórios.
8. Integração inicial com Terra.
9. Busca e habilitação explícita de projetos COPR.
10. Mensagens claras para erros e operações em andamento.

## 10. Fora do escopo inicial

- Sistema de avaliações ou comentários de usuários.
- Recomendações personalizadas.
- Loja própria de pacotes ou repositórios.
- Envio de telemetria.
- Suporte imediato a várias distribuições Linux.
- Avaliação automática da segurança ou qualidade de projetos COPR.

## 11. Diferencial do projeto

A aplicação deve se posicionar como uma loja de aplicativos para usuários de Fedora com WM: simples de usar, mas transparente sobre o gerenciamento de pacotes. O foco não é apenas oferecer um botão de instalação, e sim deixar claro de onde vem cada pacote, quais mudanças serão feitas e quais fontes estão habilitadas.

