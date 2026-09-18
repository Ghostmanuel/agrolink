# AgroLink Angola — Backend + App Móvel

Marketplace agrícola com transporte rastreado em tempo real, chat de negociação
e pagamentos angolanos (Multicaixa Express / IBAN), com comissão moderada para
a plataforma.

## 1. Base de dados — esquema e relações

```mermaid
erDiagram
    USERS ||--o{ PRODUCTS : "publica (farmer)"
    USERS ||--o{ ORDERS : "compra (buyer)"
    USERS ||--o{ ORDERS : "entrega (driver)"
    USERS ||--o| VEHICLES : "possui (driver)"
    USERS ||--o{ LOCATION_PINGS : "envia (driver)"
    USERS ||--o{ CONVERSATIONS : "participa (buyer/seller)"
    USERS ||--o{ CHAT_MESSAGES : "envia"
    PRODUCTS ||--o{ ORDERS : "é comprado em"
    ORDERS ||--o{ LOCATION_PINGS : "tem histórico de posição"
    ORDERS ||--|| PAYMENTS : "tem um"
    CONVERSATIONS ||--o{ CHAT_MESSAGES : "contém"

    USERS {
        int id PK
        string name
        string phone UK
        string password_hash
        string role "buyer | farmer | driver | admin"
        string province
        bool verified
        string iban
        string express_phone
    }
    VEHICLES {
        int id PK
        int driver_id FK
        string plate
        string model
        string vehicle_type
        float capacity_kg
    }
    PRODUCTS {
        int id PK
        int producer_id FK
        string name
        string category
        float price
        float quantity
        string unit
        string province
        string status
    }
    ORDERS {
        int id PK
        int product_id FK
        int buyer_id FK
        int driver_id FK
        float quantity
        float total
        string status "pending|confirmado|pago|a_caminho|entregue|cancelado"
        datetime created_at
    }
    LOCATION_PINGS {
        int id PK
        int order_id FK
        int driver_id FK
        float latitude
        float longitude
        float speed_kmh
        datetime created_at
    }
    CONVERSATIONS {
        int id PK
        int buyer_id FK
        int seller_id FK
        int product_id FK
    }
    CHAT_MESSAGES {
        int id PK
        int conversation_id FK
        int sender_id FK
        string content
        float proposed_price
        datetime created_at
    }
    PAYMENTS {
        int id PK
        int order_id FK UK
        string method "multicaixa_express | iban"
        string reference
        float amount
        float commission_amount
        float net_to_seller
        string status "pendente | pago | falhou"
    }
```

**Regras chave:**
- Um `Order` liga um `Product`, um `buyer` e (quando atribuído) um `driver`.
- `LocationPing` guarda o histórico de posições GPS enviadas pelo transportador
  durante uma entrega — permite reconstituir a rota percorrida, não só a última posição.
- `Conversation` liga comprador ↔ vendedor (opcionalmente a um produto), e cada
  `ChatMessage` pode transportar uma `proposed_price` para negociação de preço.
- `Payment` é único por pedido (1‑para‑1) e regista sempre o valor total,
  a comissão retida e o valor líquido a entregar ao vendedor — nada disto é
  calculado "no frontend", para que o histórico financeiro seja auditável.

## 2. Comissão da plataforma

Definida em `COMMISSION_RATE` (variável de ambiente, por defeito **4%** — uma
taxa moderada, comum em marketplaces agrícolas, que não penaliza o produtor
nem o comprador). É aplicada automaticamente em `/api/v1/payments` e fica
gravada em `Payment.commission_amount`, nunca recalculada depois.

Para mudar a taxa: `COMMISSION_RATE=0.03` (3%), por exemplo, no `.env` ou no Docker.

## 3. API (novidades desta versão)

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/v1/vehicles` | Transportador regista o seu veículo |
| POST | `/api/v1/orders/{id}/assign-driver` | Atribui um transportador a um pedido |
| WS | `/ws/location/{order_id}?token=...` | Transportador envia GPS; comprador/agricultor recebem em tempo real |
| GET | `/api/v1/orders/{id}/location` | Última posição conhecida do pedido |
| POST | `/api/v1/conversations` | Inicia conversa comprador ↔ vendedor |
| GET | `/api/v1/conversations/{id}/messages` | Histórico do chat |
| WS | `/ws/chat/{conversation_id}?token=...` | Chat em tempo real, com proposta de preço opcional |
| POST | `/api/v1/payments` | Regista pagamento (Multicaixa Express ou IBAN) e calcula a comissão |
| POST | `/api/v1/payments/{id}/confirm` | Admin confirma pagamento (em produção seria um webhook do gateway) |
| GET | `/api/v1/admin/summary` | Inclui agora comissão total ganha e pagamentos pendentes |

> **Nota sobre pagamentos reais:** este endpoint regista a intenção/instrução
> de pagamento e a comissão devida. Para debitar/creditar contas de verdade
> em Angola precisa de integrar um gateway certificado (ex: EMIS/Multicaixa
> Express API, ou um agregador como Payflex/PawaPay) — troque a lógica dentro
> de `create_payment()` pela chamada real a esse gateway, mantendo o cálculo
> de comissão como está.

## 4. O "aplicativo móvel"

Está em `mobile-app/` — uma **PWA (Progressive Web App)**: um site que se
comporta como app nativa (instala-se no ecrã principal do Android/iOS,
funciona em ecrã inteiro, ícone próprio). Não precisa de compilar nada:

1. Publique a pasta `mobile-app/` em qualquer servidor estático (Netlify,
   Vercel, Nginx, etc.) com HTTPS — obrigatório para GPS e instalação como app.
2. No telemóvel, abra o link no Chrome/Safari → "Adicionar ao ecrã principal".
3. Nas Definições (ícone ⚙️ no topo) configure o endereço do backend.

**Para uma app 100% nativa** (Google Play / App Store), a forma mais rápida de
reaproveitar este código é embrulhá-lo com o **Capacitor** (Ionic):
```bash
npm init -y
npm i @capacitor/core @capacitor/cli @capacitor/geolocation
npx cap init AgroLink com.agrolink.app
npx cap add android
npx cap add ios
# copie mobile-app/* para a pasta "www" do projeto Capacitor e:
npx cap sync
```
Isto dá-lhe binários Android/iOS reais a partir do mesmo HTML/JS, com acesso
a GPS em segundo plano, notificações push, etc.

### Ecrãs incluídos no protótipo
- **Login / Registo** com escolha de perfil (comprador, agricultor, transportador)
- **Mercado**: pesquisa e compra de produtos
- **Pagamento**: escolha Multicaixa Express ou IBAN, com a comissão explicada de forma transparente
- **Pedidos**: lista de pedidos com estado
- **Rastreio em tempo real**: mapa com a posição do veículo (WebSocket), enviada pelo GPS do telemóvel do transportador
- **Chat**: negociação de preços em tempo real entre comprador e vendedor
- **Perfil**: publicar produtos (agricultor), registar veículo e partilhar localização (transportador), painel de comissões (admin)

## 5. Correr tudo localmente

```bash
pip install -r requirements-backend.txt --break-system-packages
uvicorn app:app --reload --port 8000
# noutro terminal, sirva a pasta mobile-app/, ex:
cd mobile-app && python3 -m http.server 5500
```
Depois abra `http://localhost:5500` no telemóvel (na mesma rede Wi-Fi, usando
o IP do computador em vez de `localhost`) e configure a API em Definições
para `http://SEU_IP:8000`.

Para criar o primeiro administrador: registe um utilizador normal e depois
mude o campo `role` para `"admin"` diretamente na base de dados
(`agrolink.db`), já que o registo público só permite comprador/agricultor/transportador.
