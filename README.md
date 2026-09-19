# AgroLink Angola — versão 6.0 de teste comercial

Esta versão reúne o frontend PWA + backend FastAPI + `agrolink.db` e fecha o fluxo principal para teste:

**Cadastro → Mercado → Compra → Transporte → Confirmação das 3 partes → Pagamento pendente → confirmação administrativa/gateway → Entrega → GPS → Notificações → Chat.**

## Teste rápido local

1. `pip install -r requirements-backend.txt`
2. `python migrate_db.py`
3. `python seed_demo.py`
4. `uvicorn app:app --reload`
5. Abrir `http://127.0.0.1:8000`
6. Usar as contas de demonstração abaixo.
7. Opcional: `python smoke_test.py`

### Contas de demonstração

- Comprador: `900000001` / `Demo1234`
- Agricultor: `900000002` / `Demo1234`
- Transportador: `900000003` / `Demo1234`
- Administrador: `900000000` / `Admin1234`

**Estas contas são apenas para demonstração. Não as use em produção.**

## O que pode ser testado

### Comprador
- Criar conta / entrar / recuperar senha.
- Pesquisar produtos.
- Ver produtor, empresa/fazenda e província.
- Criar pedido com quantidade e morada.
- Escolher transportador livre.
- Confirmar dados.
- Ver as confirmações do vendedor e motorista.
- Rever dados antes de iniciar pagamento.
- Ver referência AgroLink e comissão de 4%.
- Ver notificações e conversar no chat.
- Acompanhar localização quando o motorista estiver a partilhar GPS.

### Agricultor/Vendedor
- Criar conta.
- Editar dados e empresa/fazenda.
- Publicar produtos com fotografia.
- Receber notificação de novo pedido.
- Escolher/confirmar transportador.
- Confirmar dados do pedido.
- Conversar com comprador e transportador.

### Transportador/Motorista
- Criar conta.
- Registar vários veículos.
- Fotografia, matrícula, modelo, tipo e capacidade.
- Ver pedidos atribuídos.
- Confirmar dados.
- Confirmar pagamento quando este for confirmado pelo fluxo administrativo/gateway.
- Iniciar entrega, marcar como entregue e partilhar GPS.

### Administrador
- Ver painel com utilizadores, produtos, pedidos, veículos, volume, comissão e pagamentos.
- Para demonstração, pode confirmar um pagamento pendente. Em produção esta ação deve ser substituída pelo webhook idempotente do gateway/PSP.

## Pagamentos MULTICAIXA/EMIS

O sistema **não simula uma cobrança bancária como se fosse real**. A API cria uma ordem de pagamento/referência AgroLink e mantém o estado `aguardando` até a confirmação do gateway/PSP. Para produção, é necessário contrato/credenciais do parceiro de integração e implementação de criação de pagamento + callback/webhook idempotente.

## Produção / Render

Variáveis recomendadas:

```text
DATABASE_URL=<PostgreSQL>
SECRET_KEY=<chave-forte-e-privada>
COMMISSION_RATE=0.04
RESET_DEV_MODE=false
DEMO_MODE=false
```

Start command:

```bash
./start.sh
```

O `start.sh` executa a migração e inicia o Uvicorn.

## Segurança antes do lançamento

- Não ativar `DEMO_MODE` em produção.
- Não usar as contas de demonstração em produção.
- Trocar `SECRET_KEY`.
- Recuperação de senha deve ser enviada por SMS/OTP real.
- Imagens devem migrar de Base64 no banco para object storage.
- Pagamento deve ser confirmado exclusivamente pelo webhook/retorno autenticado do PSP/gateway.
- Adicionar rate limiting, logs de auditoria, backup, HTTPS, gestão de sessões e testes de segurança.
