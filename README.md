# AgroLink Angola v12

Versão corrigida do MVP web/PWA, mantendo a arquitetura SQLite/FastAPI do v11 e corrigindo o fluxo de cadastro, mercado, pedidos, transporte, pagamentos pendentes, notificações e administração.

## Render
Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Configure as variáveis do `.env.example` no Render. Em produção, `SECRET_KEY` e `ADMIN_PASSWORD` devem ser valores fortes e privados.

## Instalação local
`pip install -r requirements.txt`
`uvicorn main:app --reload`

## Nota de produção
A integração financeira real com PSP/MULTICAIXA ainda requer contrato/credenciais do provedor. O endpoint de webhook é um ponto de extensão e não deve ser exposto como confirmação financeira sem validação de assinatura do PSP.

© 2026 Nuvem JM – Prestação de Serviços e Tecnologias de Informação, Limitada. Todos os direitos reservados.
