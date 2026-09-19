# AgroLink Angola v11

Marketplace agrícola + logística + pagamento protegido + rastreamento + chat + administração + offline-first.

Entidade: **Nuvem JM – Prestação de Serviços e Tecnologias de Informação, Limitada.**

**© 2026 Nuvem JM – Prestação de Serviços e Tecnologias de Informação, Limitada. Todos os direitos reservados.**

## Escopo v11
- Comprador, Produtor/Vendedor, Transportador e Administrador
- Marketplace, pesquisa, categorias, produtores/fazendas
- Pedidos com revisão do vendedor
- Transporte: comprador, vendedor ou transportador AgroLink
- Preço de transporte por distância/rota
- GPS/ETA e estados da entrega
- Chat contextual ao pedido
- Pagamento protegido / liquidação condicionada à entrega
- Código de confirmação e PoD
- Comissões: 4% vendedor e 1% transportador
- Admin, relatórios, notificações e auditoria
- RBAC, validações, rate limit (estrutura) e segurança
- Offline-first / fila de sincronização
- API-first para futura aplicação React Native

## Executar
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Abrir `http://127.0.0.1:8000` e `/docs`.

**Nota:** a retenção/liberação real dos fundos depende do PSP/banco e do enquadramento jurídico/contratual. O projeto modela os estados e regras, não cria uma conta escrow bancária.

## Adenda — frontend, deploy no Render e administrador (adicionado nesta revisão)

### O que foi corrigido/acrescentado nesta versão
- **CORS**: o `main.py` não tinha `CORSMiddleware`. Adicionado (`allow_origins=['*']`), senão qualquer chamada feita de um domínio diferente do backend falha com "Failed to fetch".
- **Bootstrap de administrador**: o registo público só cria `buyer`/`seller`/`transporter` (por segurança). Defina `ADMIN_PHONE` e `ADMIN_PASSWORD` (mín. 8 caracteres) nas variáveis de ambiente para criar/promover essa conta a `admin` automaticamente no arranque. Pode remover as variáveis depois do primeiro deploy — a conta já fica gravada na base de dados.
- **`/`, `/manifest.json`, `/sw.js`**: agora servem `index.html`, `manifest.json` e `sw.js` (o novo frontend, ver abaixo) se esses ficheiros existirem na raiz do projeto, para poder publicar backend + app no mesmo domínio do Render.

### Frontend (`index.html`, `manifest.json`, `sw.js`)
Não existia nenhum frontend nesta versão — só uma página de apresentação. Foi construído um novo, uma PWA (instalável no ecrã principal do telemóvel), já ligada às rotas reais deste backend (`/api/auth/...`, `/api/orders/...`, `/api/deliveries/...`, `/api/transporters/available`, etc.). Cobre:
- Login / registo com os três perfis públicos, incluindo BI/NUC do transportador (nunca exposto por completo a outros utilizadores — a API já o mascara).
- Mercado, criação de pedidos, aceitação/recusa pelo vendedor.
- Atribuição de transportador (modo `agrolink`) com o código de confirmação de entrega de 6 dígitos.
- Pagamento (Multicaixa Express / IBAN) com chave de idempotência gerada no cliente.
- Rastreio em tempo real (mapa) via WebSocket, alimentado pelo GPS real do telemóvel do transportador.
- Chat por pedido (WebSocket).
- Notificações.
- Painel do administrador: métricas e libertação de pagamento por pedido entregue e pago.

Testado com um teste automatizado que percorre o fluxo completo (registo → produto → pedido → aceitação → atribuição de transportador → pagamento → confirmação de entrega) usando `TestClient`, incluindo o arranque do administrador.

### Publicar no Render
1. **Build Command**: `pip install -r requirements.txt`
2. **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   (repare no `app.main:app`, não `app:app` — o código está dentro da pasta `app/`.)
3. Variáveis de ambiente mínimas: `SECRET_KEY` (algo forte e aleatório), `ADMIN_PHONE`, `ADMIN_PASSWORD`.
4. O SQLite (`agrolink_v11.db`) é recriado a cada deploy no plano gratuito do Render (disco efémero) — para persistência real, troque `DATABASE_URL` por uma base de dados gerida (o adaptador PostgreSQL ainda não está implementado em `db.py`; hoje só aceita `sqlite:///`).

