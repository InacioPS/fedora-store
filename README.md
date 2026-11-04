# Fedora Store

Loja gráfica para explorar aplicativos e pacotes Fedora, com foco em transparência de origem e compatibilidade com sessões de window manager.

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

A interface usa GTK4, libadwaita, ícones do tema instalado e o esquema de cores do sistema. O catálogo atual é de demonstração; nenhuma mudança real no sistema é feita.
