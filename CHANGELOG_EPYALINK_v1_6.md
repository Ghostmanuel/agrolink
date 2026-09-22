# EPYALINK v1.6 — Auditoria estrutural de i18n + Admin + perfis

## Correções
- Corrigido erro estrutural no frontend: `TECH` era referenciado pelo sistema i18n sem declaração, podendo interromper `renderAll()` e deixar o seletor de idioma sem funcionamento.
- Seletor de idioma reforçado com `pointer-events`, `z-index`, `click` e `pointerdown` próprios.
- Tradução dinâmica agora suporta textos mistos/dinâmicos, incluindo mensagens com IDs, valores e estados.
- `alert()` e `prompt()` passam pelo tradutor para mensagens da interface.
- Painel administrativo usa `adminT()`/`adminValue()` diretamente, incluindo Users/Utilizadores, Seller/Vendedor, Buyer/Comprador e Transporter/Transportador.
- Roles internos permanecem canónicos (`buyer`, `seller`, `private_transporter`, `transport_company`, `admin`) e apenas a apresentação é traduzida.
- Perfil próprio, perfis públicos e Chat usam `roleLabel()`.
- Seller/farmer panel passou a construir labels e placeholders através do i18n.
- Estados técnicos comuns foram adicionados ao mapa técnico para PT/EN/FR/ES.
- Catálogos PT/EN/FR/ES foram auditados; as oito chaves auxiliares faltantes foram cobertas por `EXTRA_I18N`.
- Mantida a integração KambaSMS exclusivamente no backend; a API key não é colocada no frontend.

## Validação
- JavaScript: `node --check` aprovado após extração dos scripts do `index.html`.
- Python: `python -m py_compile` aprovado para o backend.
- Auditoria estática dos catálogos: PT/EN/FR/ES sem lacunas das chaves principais do catálogo inglês após o fallback auxiliar.

## Nota
Os idiomas nacionais angolanos continuam individualmente previstos na arquitetura. Não são apresentados como traduções completas quando ainda não existe conteúdo linguístico validado para todo o produto.
