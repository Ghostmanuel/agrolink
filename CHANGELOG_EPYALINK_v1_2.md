# EPYALINK v16.2.2 — estabilização para demonstração

## Correções
- Menu global corrigido para usar `☰` e permanecer funcional após troca de ecrã.
- Sistema de tradução reforçado para estados, papéis, métricas e chaves técnicas como `buyer`, `seller`, `orders`, `delivered` e `unread_notifications`.
- Tradução dinâmica passa a reconstruir a partir de uma forma canónica, evitando que textos fiquem presos no idioma anterior.
- Recuperação de palavra-passe preparada para KambaSMS OTP real; código não é exposto quando o fornecedor está configurado.
- Proteção anti-abuso local para recuperação: máximo configurável por hora e intervalo mínimo de 60 segundos.
- Código de confirmação da entrega deixou de ser devolvido pela API de atribuição do transportador.
- Modalidade “O vendedor entrega” passou a aceitar e guardar o preço definido pelo vendedor; EPYALINK não calcula nem impõe o valor.
- Migração automática adiciona a coluna `provider` aos tokens de recuperação em bases antigas.
- Service Worker versionado para reduzir risco de cache antigo.
- Removido decorator duplicado da rota de registo.

## Limitações conhecidas antes da produção
- Para SMS real é necessária uma `KAMBASMS_API_KEY` válida no Render.
- Pagamentos MULTICAIXA/PSP continuam dependentes de integração e credenciais reais.
- Traduções para línguas nacionais continuam preparadas arquiteturalmente e precisam de tradução/validação humana antes de serem apresentadas como completas.
