# AgroLink Angola — Escopo v11

## Negócio
Comprador gratuito; produtor 4% sobre venda concluída; transportador 1% sobre transporte concluído.

## Fluxo
Produto → quantidade → endereço → revisão do vendedor → conversa → decisão de transporte → confirmação → pagamento → entrega → código/PoD → liquidação.

## Transporte
- comprador: 0 Kz;
- vendedor: pode cobrar entrega própria;
- AgroLink: somente quando comprador e vendedor concordarem;
- distância por rota real;
- GPS, ETA e estados da viagem.

## Pagamento protegido
O pagamento permanece pendente de liquidação até às condições de entrega serem cumpridas. O código pertence ao comprador. A liquidação real depende do PSP/banco e da estrutura contratual.

## Segurança
RBAC, validação frontend/backend, rate limiting/anti-bot, BI protegido, blind hash, auditoria, matrícula por Strategy Pattern, webhooks idempotentes, PoD e geofencing.

## Baixa conectividade
Offline-first, fila de sincronização, GPS/eventos locais, pontos/Agentes AgroLink e futura possibilidade de SMS/USSD. Operações financeiras não são liquidadas apenas em modo offline.

## Admin
Utilizadores, produtores, transportadores, veículos, produtos, pedidos, pagamentos, comissões, transportes, chat, notificações, relatórios, insights, segurança e configurações.

## Propriedade
Nuvem JM – Prestação de Serviços e Tecnologias de Informação, Limitada.
© 2026. Todos os direitos reservados.
