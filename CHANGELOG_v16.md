# AgroLink Angola v16

## Correção do cadastro de Empresa Transportadora
- Adicionado campo visível e obrigatório “Nome da empresa transportadora” quando o perfil é Empresa Transportadora.
- O nome informado é enviado como `company_name` para o backend.
- BI deixou de ser exigido visualmente para empresa transportadora; continua obrigatório para Transportador Particular/Independente.
- Mantida a validação backend existente que exige `company_name` para `transport_company`.
- Base preservada: AgroLink Angola v15, `main.py` mantido.
