# AgroLink Angola v15 — evolução incremental sobre v14

Esta versão foi construída diretamente sobre o AgroLink Angola v14, mantendo `main.py` como backend principal. Não usa o antigo `app.py`.

## Implementado nesta v15

1. **Rotas e distância rodoviária**
   - integração configurável com OSRM para distância e ETA por estrada;
   - geocodificação configurável via Nominatim;
   - usa origem do produto/produtor quando o utilizador não informa origem;
   - fallback geográfico/manual para ambientes sem serviço de rotas;
   - tarifa continua configurável no servidor.

2. **Ficheiros privados**
   - upload autenticado para fotos/documentos;
   - validação de tipo e tamanho;
   - armazenamento fora da pasta pública;
   - acesso protegido por autenticação e autorização;
   - administrador e empresa transportadora podem aceder apenas aos documentos autorizados.

3. **Sessão persistente**
   - JWT assinado pelo backend;
   - expiração configurável;
   - compatível com múltiplas instâncias do backend, ao contrário do dicionário de tokens em memória da v14.

4. **Administração ampliada**
   - suspensão/ativação de utilizadores;
   - métricas de liquidações;
   - gestão de liquidações;
   - auditoria das operações administrativas.

5. **Liquidação financeira interna**
   - cálculo da comissão do vendedor (4%);
   - cálculo da comissão do transportador independente (1%);
   - criação de registos de liquidação após entrega confirmada e pagamento confirmado;
   - saldo líquido por beneficiário;
   - marcação administrativa como pago com referência de transferência;
   - consulta de liquidações do próprio utilizador.

## Mantido deliberadamente como DEMO / não-real

### Ponto 1 — pagamento real EMIS/PSP
A aplicação continua a **não confirmar dinheiro real**. Os endpoints de pagamento e webhook continuam demonstrativos até existir integração/credenciais/contrato com o PSP/EMIS e respetiva validação técnica.

### Ponto 6 — chat multimédia
O chat continua textual nesta versão. Não foi transformado em chat de fotos/áudio/vídeo em tempo real.

## Observações de produção

- O OSRM/Nominatim públicos servem para demonstração e testes. Para operação comercial, configurar serviços de roteamento/geocodificação adequados e respeitar os seus termos e limites.
- Para Render, configurar `FILE_STORAGE_DIR` para um storage persistente ou substituir o backend de ficheiros por armazenamento S3-compatible. O armazenamento local pode ser efémero dependendo da infraestrutura.
- Definir `SECRET_KEY` forte e `BI_ENCRYPTION_KEY` própria em produção.
- Instalar as dependências de `requirements.txt`, incluindo PyJWT.
