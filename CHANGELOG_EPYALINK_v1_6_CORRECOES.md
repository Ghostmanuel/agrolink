# EPYALINK v1.6 — Correções de cadastro, fotografia e recuperação

Base: EPYALINK_v1_6_i18n_admin_perfis_kambasms.zip

## Correções aplicadas

- Removida a implementação duplicada do `registerForm.onsubmit` no `index.html`.
- Cadastro passa a exigir fotografia de perfil e envia a fotografia no mesmo pedido de cadastro.
- Validação no frontend: JPG, PNG ou WebP, máximo 5 MB.
- Validação correspondente no `main.py`.
- Mantido o armazenamento da fotografia usando a mesma transação SQLite do cadastro.
- Recuperação de palavra-passe: limpeza do código anterior, preparação correta do Turnstile de redefinição e mensagens de fluxo mais claras.
- Mantido KambaSMS como fornecedor de OTP quando configurado.
- O OTP KambaSMS continua a ser verificado no endpoint do provedor, sem expor a API key no frontend.
- O token local de recuperação só é aceite quando o provedor é `local`.
- Mantida a arquitetura de idiomas, perfis, administração, chat, produtos e transporte da v1.6.

## Observação de produção

As fotografias continuam a usar `FILE_STORAGE_DIR`. Em Render, esse diretório deve estar associado a armazenamento persistente ou substituído por storage de objetos antes do lançamento comercial, para que ficheiros não dependam do filesystem efémero da instância.
