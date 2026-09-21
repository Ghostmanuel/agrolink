# AgroLink Angola v16.2 — Escopo comercial ampliado

Base preservada: v16.1. Esta versão amplia o escopo sem substituir a arquitetura existente.

## Implementado
- Perfil com fotografia de identificação e atualização de fotografia.
- Perfil público de produtor/empresa com foto, província, fazenda/empresa, produtos e avaliações, sem expor o endereço residencial exato.
- Foto de perfil reutilizável como identidade no chat.
- Mercado com filtros por província, unidade e faixa de preço.
- Favoritos de produtos.
- Avaliações 1–5 após entrega concluída.
- Verificação de perfil pelo administrador.
- Centro de disputas do pedido + resolução administrativa.
- Prova de entrega com fotografia e coordenadas opcionais.
- Dashboards pessoais básicos por perfil.
- Chat associado ao pedido com contexto do produto e identidade do remetente.
- Fluxo de transporte explícito:
  - Vou buscar → 0 Kz, sem cálculo de transporte.
  - O vendedor entrega → preço definido pelo vendedor; AgroLink não calcula nem impõe.
  - Transportador AgroLink → cotação com rota + carga + capacidade do veículo.
- Cotação AgroLink com conversão de carga para kg para kg, tonelada, saco e unidade e fator de capacidade.
- Tarifas de transporte configuráveis via `app_settings`.
- Stock reservado no momento da criação do pedido e reposto quando o vendedor rejeita o pedido.
- Insights de mercado: produtos vendidos, regiões compradoras, stock baixo e leitura do catálogo.
- Menu ⋮ institucional compacto e Sair dentro do menu.

## Mantido
- Turnstile, autenticação, recuperação de palavra-passe, BI protegido, auditoria, pagamentos, liquidação, GPS, notificações, administração e integração preparada para PSP/MULTICAIXA/EMIS.

## Validação
- `py_compile` para `main.py`, `schemas.py` e `db.py`.
- `node --check` sobre os blocos JavaScript do `index.html`.
- Migração SQLite validada para as novas tabelas e definições de tarifa.

## Dependências externas que continuam por integrar
- MULTICAIXA/EMIS/PSP real requer credenciais/contratos oficiais.
- SMS/WhatsApp/push requer provedor/infraestrutura.
- Roteamento depende do serviço configurado e tem fallback.
