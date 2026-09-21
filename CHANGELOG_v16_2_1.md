# AgroLink Angola — v16.2.1

Base: v16.2.0 recuperada do commit `cd8212c`.

## Estabilização
- Service Worker com cache versionado `agrolink-v16-2-1`.
- Navegação/HTML usa network-first para evitar interface antiga após deploy.
- Registo do Service Worker com cache-buster `v=16.2.1`.
- Cabeçalho inicial consistente com menu `⋮`; “Sair” permanece dentro do menu institucional.
- Removida declaração duplicada de `publish()`.
- Publicação de produtos usa fotografia de ficheiro (`pPhotoFile`) de forma consistente com o endpoint de upload.
- Versão FastAPI atualizada para `16.2.1`.
- Banco de dados e estrutura comercial da v16.2.0 preservados.

## Regra de deploy
Esta versão deve ser publicada como um único commit, mantendo a branch `recuperar-16-2-0` como ponto seguro até a validação final.
