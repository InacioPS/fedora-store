# Fedora Store

Loja gráfica para explorar aplicativos e pacotes Fedora, com foco em transparência de origem e compatibilidade com sessões de window manager.

## Prévia

![Catálogo da Fedora Store](preview/Screenshot%20from%202026-11-08%2000-11-28.png)

![Configurações da Fedora Store](preview/Screenshot%20from%202026-11-08%2000-28-00.png)

## Ambiente de desenvolvimento

Requer Nix com flakes e direnv. Na primeira utilização:

```sh
direnv allow
```

Ou entre no shell manualmente:

```sh
nix develop
```

## Executar

```sh
python -m fedora_store
```

A interface usa GTK4, libadwaita, ícones do tema instalado e o esquema de cores do sistema. O ícone de aplicativos no canto superior esquerdo permite escolher e salvar o estilo de navegação **Topnav** ou **Sidebar lateral**. Em **Configurações**, o usuário escolhe fontes de terceiros; uma definição Terra já existente é apenas habilitada, sem sobrescrever o arquivo do repositório. Ao abrir e antes de aplicar atualizações, verifica os metadados com `dnf --refresh` em segundo plano; se a verificação falhar, mostra os dados cacheados do DNF. Ativar fontes de terceiros ou instalar/remover aplicativos solicita autorização do sistema por Polkit.

Em **Configurações → Execução em segundo plano**, **Manter na bandeja** mantém o processo ativo ao fechar a janela e expõe o ícone do aplicativo na bandeja compatível com StatusNotifierItem. **Iniciar ao entrar na sessão** cria `~/.config/autostart/fedora-store.desktop`, inicia oculto na bandeja e envia uma notificação quando houver atualizações. Desativar a bandeja também desativa a inicialização em segundo plano.

Em **RPM local**, arraste ou escolha um arquivo `.rpm` para revisar nome, versão, arquitetura, tamanho e resumo antes da instalação. A instalação usa `pkexec dnf install -y /caminho/absoluto/do-pacote.rpm`; o DNF resolve dependências e o Polkit solicita autorização.

## Construir RPM

O primeiro pacote pode ser construído dentro do shell Nix:

```sh
nix develop
./packaging/build-rpm.sh
```

O artefato aparece em `.rpmbuild/RPMS/noarch/fedora-store-0.1.1-1.noarch.rpm`. O script cria um arquivo fonte limpo, força os caminhos Fedora (`/usr`) mesmo quando o `rpmbuild` vem do Nix e valida o arquivo `.desktop`.
