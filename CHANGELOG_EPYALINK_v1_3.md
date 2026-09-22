# EPYALINK v1.3 — correção estrutural de frontend/i18n + KambaSMS

- Corrigido o sistema de idioma para traduzir também o ecrã de autenticação e conteúdo criado dinamicamente.
- Observador de DOM passou a acompanhar `body`, não apenas `#app`.
- Catálogo central de frases PT/EN/FR/ES para mercado, cadastro, pedidos, transporte, chat, perfil, pagamentos, notificações, administração e recuperação de palavra-passe.
- Tradução de placeholders, títulos e aria-labels preservada após reconstrução de componentes.
- Canonicalização baseada em catálogo evita ficar preso ao idioma anterior.
- EPYALINK definido como nome padrão do backend.
- Recuperação KambaSMS permanece exclusivamente no backend; a API key deve ser configurada como secret no Render.
- OTP local limitado a 5 minutos, alinhado ao retorno de validade do provedor.
- Não inclui nenhuma API key no código, ZIP ou frontend.
