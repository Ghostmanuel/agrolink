# AgroLink Angola v16.1

Evolução incremental da v16, preservando `main.py`.

## Implementado
- Painel Admin com Relatórios, Auditoria e Configurações.
- Endpoint de auditoria com filtros por ação/módulo e registo do acesso à auditoria.
- Relatórios comerciais/operacionais e exportação JSON pelo painel.
- Configurações administrativas persistentes em `app_settings`.
- Menu institucional: Quem somos, missão, visão, visão futurista, como funciona, sobre, termos, privacidade, ajuda e contactos.
- Contactos oficiais da Nuvem JM e copyright.
- Upload de fotografia para produtos com armazenamento privado e endpoint de imagem do produto.
- Fotografias no chat através de anexos protegidos.
- Auditoria do envio de mensagens e anexos.
- Migração aditiva para `chat_messages.attachment_file_id` e `app_settings`.

## Mantido como antes
- Pagamentos EMIS/PSP reais continuam fora da versão até existir integração/credenciais oficiais.
- Chat multimédia foi agora acrescentado nesta versão; vídeo/áudio ainda não fazem parte do escopo.
- Não foi reintroduzido `app.py`; a base continua a ser a v16/main.py.
