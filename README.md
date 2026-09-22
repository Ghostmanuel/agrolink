# EPYALINK

Plataforma agrícola digital — **Do campo ao mercado, conectado.**

## Estrutura canónica

- `main.py` — aplicação FastAPI e endpoints.
- `db.py` — SQLite, esquema e migrações de compatibilidade.
- `security.py` — palavras-passe, hashes cegos e encriptação AES-GCM de dados sensíveis.
- `schemas.py` — contratos Pydantic da API.
- `config.py` — configuração exclusivamente por variáveis de ambiente.
- `index.html` — frontend PWA mobile-first.
- `manifest.json` — identidade PWA EPYALINK.
- `sw.js` — cache do app shell; nunca cacheia `/api/` nem WebSockets.
- `requirements.txt` — dependências usadas diretamente pelo código actual.

## Arranque

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Para desenvolvimento local, pode usar `APP_ENV=development` e desactivar temporariamente o Turnstile no ambiente de teste.

## Segurança

- Turnstile é validado no backend.
- BI é armazenado cifrado com AES-GCM e acompanhado por hash cego para pesquisas.
- Tokens JWT são validados no backend e as contas suspensas são rejeitadas.
- Ficheiros privados exigem autorização no backend.
- Recuperação de palavra-passe usa KambaSMS em produção; o modo demo deve permanecer desligado.
- WebSockets exigem sessão válida e autorização para o pedido.
- CORS é aberto apenas quando necessário; para ambientes com origens conhecidas, configure `CORS_ALLOW_ORIGINS`.

## Base de dados e armazenamento

O projecto actual usa SQLite. Para uma instalação nova, defina uma `DATABASE_URL` persistente (por exemplo `sqlite:///./epyalink.db`). **Não altere a `DATABASE_URL` de uma instalação existente sem primeiro preservar a base de dados**, porque isso pode fazer a aplicação iniciar com uma base vazia.

`FILE_STORAGE_DIR` também deve apontar para armazenamento persistente em produção; caso contrário, fotografias e documentos podem desaparecer quando o ambiente for recriado.

## Recuperação por SMS

Defina no ambiente de produção:

- `PASSWORD_RESET_SMS_PROVIDER=kambasms`
- `KAMBASMS_API_KEY=<segredo>`
- `KAMBASMS_BASE_URL=https://api.kambasms.ao`
- `PASSWORD_RESET_DEMO=false`
- `PASSWORD_RESET_TTL_MINUTES=5`
- `PASSWORD_RESET_RATE_LIMIT_PER_HOUR=3`

Nunca coloque chaves ou segredos reais no repositório ou no chat.
