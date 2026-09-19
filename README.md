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
