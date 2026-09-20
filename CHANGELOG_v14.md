# AgroLink Angola v14 — evolução incremental sobre o v13

## Base preservada
- Mantido `main.py` como aplicação FastAPI principal.
- Mantida a estrutura e os endpoints existentes do v13.
- Não foi usado `app.py` como base.
- Migrações SQLite são aditivas e compatíveis com bases anteriores.

## Evoluções implementadas
- Cadastro separado para `Empresa Transportadora` e `Transportador Particular / Independente`.
- Compatibilidade com contas antigas `transporter`.
- Tabela de empresas transportadoras.
- Gestão de motoristas por empresa, sem criar uma terceira categoria de utilizador.
- BI/documentos de motoristas armazenados com AES-GCM para novos registos, com chave configurável.
- Acesso completo ao BI protegido por endpoint administrativo e auditoria.
- BI não é devolvido no perfil normal; apenas versão mascarada.
- Veículos preparados para associação a empresa e motorista.
- Endpoints para criar/listar motoristas e consultar documentos autorizados.
- Frontend de cadastro atualizado para os dois tipos de transporte.
- Dependência `cryptography` adicionada.
- Versão da aplicação atualizada para 14.0.0.

## Ainda não implementado nesta versão
- Integração real com MULTICAIXA/PSP.
- Roteamento rodoviário real e ETA por serviço de mapas.
- Armazenamento privado de fotos/documentos com object storage.
- Sessões persistentes/JWT para produção.
- Painel administrativo completo conforme todo o escopo aprovado.
- Chat multimédia completo.
- Liquidação/payout real.
