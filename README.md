# AgroLink Angola v15

Versão de correção do MVP/PWA.

## Correções principais
- Corrigido o fluxo de criação de pedidos e adicionada migração compatível com bases SQLite antigas.
- Recuperação de palavra-passe com OTP de 6 dígitos; em demo o código é exibido, em produção deve ser enviado por SMS/WhatsApp.
- Cloudflare Turnstile no login, cadastro e recuperação. O backend valida o token via Siteverify.
- Service Worker/PWA atualizado para v13.
- Webhook de pagamento exige segredo de servidor; a integração PSP real continua necessária antes de produção.

## Render
Start Command:
`uvicorn main:app --host 0.0.0.0 --port $PORT`

Configure `APP_ENV=production`, `SECRET_KEY`, `TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY` reais. Os testes do Turnstile fornecidos no `.env.example` são apenas para desenvolvimento/demo.

Cloudflare Turnstile exige validação server-side; os tokens expiram em 5 minutos e são de uso único.


## v15 — serviços configuráveis
`ROUTING_BASE_URL`, `GEOCODING_BASE_URL`, `JWT_EXPIRE_MINUTES`, `FILE_STORAGE_DIR` e `MAX_UPLOAD_BYTES` podem ser configurados no ambiente.

### Recuperação de palavra-passe (v16.2.2)
- OTP por SMS preparado para KambaSMS através das variáveis `KAMBASMS_API_KEY` e `PASSWORD_RESET_SMS_PROVIDER=kambasms`.
- O backend gera/valida a recuperação sem expor o código em produção; quando o provedor KambaSMS está configurado, o OTP é enviado pelo endpoint `/otp/send` e validado pelo endpoint `/otp/verify`.
- Há limite local de 3 solicitações por hora por conta e intervalo mínimo de 60 segundos.
- `PASSWORD_RESET_DEMO=true` é apenas para demonstração/teste e pode devolver o OTP local na resposta. Não usar em produção.
