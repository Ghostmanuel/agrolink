# AgroLink Angola v9

Versão integrada para testes comerciais do AgroLink Angola.

## Incluído
- Cadastro com validação server-side e perfis comprador, agricultor/vendedor e transportador/motorista.
- Recuperação e alteração de palavra-passe.
- Mercado, produtos, transportes, pedidos, chat, GPS e notificações.
- Confirmação do comprador, vendedor e transportador antes do pagamento.
- Pagamentos **sem opção presencial**: Referência MULTICAIXA, MULTICAIXA Express/GPO, IBAN e KWiK/telefone.
- Comissão AgroLink configurada em 4%.
- Painel administrativo para utilizadores, operações, pagamentos e comissão.
- IA AgroLink local para publicidade e insights, sem chave externa obrigatória.
- Adaptador de backend para um PSP/agregador como ProxyPay em modo sandbox/configurável. As credenciais nunca ficam no frontend.
- Webhook idempotente para confirmação de pagamentos eletrónicos e histórico de eventos.
- IBAN/KWiK: para proteger a comissão e o controlo da plataforma, os dados apresentados são os dados de recebimento do AgroLink (`AGROLINK_IBAN` / `AGROLINK_KWIK_PHONE`), não o IBAN/telefone pessoal do vendedor. O AgroLink faz o acerto ao vendedor segundo o modelo comercial definido.

## Teste local
```bash
pip install -r requirements-backend.txt
python migrate_db.py
python seed_demo.py
uvicorn app:app --reload
```

## Configuração de pagamentos
Por defeito, `PAYMENT_PROVIDER=sandbox`, portanto a aplicação gera referências de demonstração e **não** marca uma transação como paga só porque uma referência foi criada.

Para ligar um provedor contratado, configure no ambiente do backend/Render:
- `PAYMENT_PROVIDER=proxypay`
- `PROXYPAY_BASE_URL`
- `PROXYPAY_API_KEY`
- `MULTICAIXA_ENTITY` quando aplicável
- `PAYMENT_REFERENCE_DAYS`
- `PAYMENT_WEBHOOK_TOKEN`

Para IBAN/KWiK da plataforma:
- `AGROLINK_BENEFICIARY_NAME`
- `AGROLINK_BANK`
- `AGROLINK_IBAN`
- `AGROLINK_KWIK_PHONE`

Nunca coloque API keys no React/HTML/JavaScript do cliente.

## Fluxo de pagamento
Pedido → revisão das 3 partes → método → dados de pagamento → pagamento → confirmação do gateway/PSP → `pago` → comissão 4% → acerto ao vendedor → entrega.

IBAN e KWiK/telefone ficam `aguardando` até confirmação definida pela operação/PSP. O botão administrativo de confirmação existe para testes/controlos internos; em produção, a confirmação deve vir do fluxo financeiro contratado e auditado.

## Métodos removidos
Pagamento presencial não faz parte desta versão. O chat pode ser usado para comunicação operacional, mas o sistema não oferece um método para registar ou concluir pagamentos fora da plataforma.
