# AgroLink Angola — MVP Completo

## O que foi construído
- API profissional em FastAPI
- PostgreSQL via Docker
- Autenticação com JWT
- Registo de compradores, agricultores e transportadores
- Marketplace
- Publicação de produtos
- Criação e consulta de pedidos
- Interface web Streamlit para demonstração
- Docker Compose

## Executar backend + PostgreSQL
```bash
docker compose up --build
```

API: http://localhost:8000
Swagger: http://localhost:8000/docs

## Executar interface
Em outro terminal:
```bash
cd frontend
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Observação
Esta versão é um MVP funcional para demonstração e desenvolvimento. Antes de produção devem ser adicionados OTP por telefone, recuperação de conta, RBAC completo, pagamentos reais através de parceiros, USSD, GPS, armazenamento de imagens, notificações, auditoria, backups, monitorização, testes, proteção de dados e revisão de segurança.

## Roadmap comercial
1. Validar marketplace em uma província-piloto.
2. Integrar transportadores.
3. Integrar pagamentos.
4. Adicionar USSD.
5. Criar app Android/iOS consumindo a mesma API.
6. Escalar infraestrutura conforme utilização.
