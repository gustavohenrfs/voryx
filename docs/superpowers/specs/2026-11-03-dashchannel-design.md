# DashChannel — Design

Data: 2026-11-03
Status: rascunho para aprovação

## 1. Intenção

Agência de modelos adultas opera grupos/canais de **prévias +18** no Telegram. Em cada grupo, ~3 modelos postam mídia; as próprias modelos cuidam do x1/upsell no privado. O DashChannel tira o trabalho repetitivo de volta disso:

- **agendar posts** de cada conta de modelo no grupo de prévias;
- **operar os grupos** (status, membros, admins, solicitações de entrada, remover/banir);
- **saber quando uma conta caiu**, sem loop de reconexão.

É um SaaS pequeno usado pelo dono (admin) e por parceiros (outras agências), cada um com suas modelos.

## 2. Usuários e volume

- 3 usuários no início: 1 admin (dono) + 2 parceiros. Admin cria os logins; não há cadastro aberto.
- Cada usuário: ~2 grupos de prévias, ~3 modelos por grupo → ~18 contas (≈25 com reservas).
- Volume baixo: dezenas a poucas centenas de ações/dia no total. Confiabilidade > escala.
- Quem agenda os posts é o usuário do painel (dono/parceiro), não as modelos. Modelos não têm login.

## 3. Objetivos

1. Conectar conta Telegram (número + api_id + api_hash → código → 2FA se houver) e guardar a StringSession criptografada.
2. Painel de grupos/canais: status (acessível ou não pela conta gestora), nº de membros, lista de admins e suas permissões.
3. Solicitações de entrada: **modo por grupo**, trocável a qualquer hora:
   - `auto` — aprova todo mundo, com throttle;
   - `manual` — lista de pendentes no painel com aprovar/rejeitar individual e "aprovar todos".
4. Membros: listar/buscar, remover (kick) e banir pelo painel.
5. Posts agendados: por conta, para um grupo, texto + mídia (foto/vídeo, álbum até 10), horário exato ou "postar agora"; editar/cancelar antes de sair; status e erro visíveis.
6. Health check: detectar conta morta e marcá-la `dead` no painel, sem reconectar em loop.
7. Isolamento total entre usuários: um parceiro nunca vê nem altera nada de outro. Admin vê tudo.

## 4. Não-objetivos

- **Conversas/reações automáticas encadeadas entre contas** para simular interação espontânea (jitter "humano", variação de texto, cadeia A→B→C). Fora de escopo, por decisão explícita. Cada post agendado é independente; a interação entre as modelos continua sendo feita por elas.
- Executável desktop. É só site.
- Cobrança/planos, cadastro self-service.
- Proxy por conta (v1 conecta direto da VPS).
- Posts recorrentes.
- Escala horizontal, filas distribuídas, Redis, Kubernetes, microserviços.

## 5. Anti-objetivos (falha mesmo que "funcione")

- Vazamento entre usuários (parceiro vê sessions, grupos ou membros de outro).
- Session ou api_hash em claro no banco, log ou resposta da API.
- Conta tomar flood/ban por causa do painel (ignorar FloodWait, disparar aprovações em rajada).
- Loop de reconexão em conta morta.
- Post agendado que some sem erro visível ou sai duplicado.

## 6. Arquitetura (decidida)

```
Vercel (Next.js)  ──HTTPS──>  nginx (VPS, certbot)  ──>  app (FastAPI + Telethon, 1 processo asyncio)
                                                            │
                                                            └── postgres (mesma VPS, docker)
                                                            └── volume /data/media
```

- **Um processo**: FastAPI e todos os clientes Telethon no mesmo event loop. Um `ClientManager` mantém `account_id → TelegramClient` em memória. Motivo: login em duas etapas precisa do mesmo cliente vivo; ações do painel (postar agora, banir) chamam o cliente direto. Custo aceito: deploy reconecta as contas (segundos).
- **Postgres como fila**: tabela `jobs`; loop interno do app busca jobs vencidos a cada ~3s com `SELECT ... FOR UPDATE SKIP LOCKED`. Sem Redis/ARQ.
- **Containers**: `app` (mem_limit 1g) e `postgres` (mem_limit 512m). nginx/certbot no host (a VPS já roda outro SaaS; reaproveitar o nginx existente, adicionando um server block).
- Stack: Python 3.12, FastAPI, Telethon, SQLAlchemy 2 (async) + asyncpg, Alembic, Pydantic v2; Next.js (App Router) + Tailwind; PostgreSQL 16.

### Camada Telegram isolada

Todo acesso ao Telethon passa por uma interface `TelegramGateway` (enviar código, login, listar diálogos, participantes, admins, pendentes, aprovar/rejeitar, kick/ban, enviar mensagem/álbum, get_me). Implementação real usa Telethon; testes usam um fake. Nenhum endpoint importa Telethon direto.

## 7. Fluxos

### 7.1 Conectar conta
1. `POST /accounts/login/start {phone, api_id, api_hash}` → cria cliente com `StringSession()` vazia, `send_code_request`; guarda login pendente em memória (`login_id`, TTL 10 min, dono = usuário).
2. `POST /accounts/login/code {login_id, code}` → `sign_in`. Se `SessionPasswordNeededError` → resposta `needs_password`.
3. `POST /accounts/login/password {login_id, password}` → `sign_in(password=...)`. Senha nunca é persistida nem logada.
4. Sucesso → salva `session_enc`, `api_hash_enc`, `api_id`, `phone`, `tg_user_id`, nome; registra no `ClientManager`; dispara sync de diálogos.
- Erros mapeados: código inválido/expirado, número banido, flood wait (mostra quanto esperar).

### 7.2 Importar session (contingência TData)
`POST /accounts/{id}/session` aceita uma StringSession nova (colada pelo usuário) para reviver uma conta `dead`. Integração automática com a API do TData fica atrás de um adaptador `SessionRestorer` com implementação nula até o contrato da API do TData ser definido.

### 7.3 Health check
- Na inicialização e a cada 10 min por conta: `get_me()`.
- Erros fatais → `status = dead`, `dead_reason`, desconecta, **não tenta de novo**: `AuthKeyUnregisteredError`, `UserDeactivatedError`, `UserDeactivatedBanError`, `SessionRevokedError`, `AuthKeyDuplicatedError`.
- Erro de rede → reconexão do próprio Telethon (`connection_retries` limitado, ex.: 5); depois disso `status = offline` e nova tentativa só no próximo ciclo de health check.
- Status possíveis: `online`, `offline`, `dead`, `connecting`.
- Qualquer job de uma conta `dead` falha imediatamente com erro claro.

### 7.4 Sincronizar grupos
- Ao conectar e sob demanda ("Atualizar"), lista diálogos onde a conta é admin (canais e supergrupos). Usuário escolhe quais importar.
- Cada grupo importado tem uma **conta gestora** (a que executa aprovações, kick/ban e leitura de membros). Trocável no painel.
- Snapshot salvo: título, username, tipo, nº de membros, admins (user_id, nome, permissões resumidas), `last_synced_at`. Re-sync a cada 30 min e no botão.
- Status do grupo: `ok` (conta gestora online e com acesso) / `sem_acesso` / `conta_caida`.

### 7.5 Solicitações de entrada
- Pendentes lidos via `messages.GetChatInviteImporters(requested=True)` na sincronização (a cada 2 min para grupos ativos) e reagindo a `UpdatePendingJoinRequests`.
- Modo `auto`: cada pendente vira job `approve_join`; o executor aplica **throttle por conta** (1 aprovação a cada 2–4 s, máx. 300 por hora por conta). Throttle serve para respeitar rate limit, não para disfarce.
- Modo `manual`: pendentes aparecem no painel; aprovar/rejeitar gera job; "aprovar todos" usa `HideAllChatJoinRequestsRequest(approved=True)` (1 chamada).
- Pendentes ficam registrados em `join_requests` com status final e quem decidiu (auto/usuário).

### 7.6 Membros
- Listagem paginada sob demanda (não persistir membros de todos os grupos; cache curto em memória ok), busca por nome/username.
- Remover = ban + unban imediato (kick). Banir = `EditBanned` com `view_messages=False`. Ambos registram em `action_logs`.

### 7.7 Posts agendados
- Campos: conta, grupo, texto (até 4096; 1024 se houver mídia — validado), mídias (0–10), `run_at` (armazenado em UTC; UI em America/Sao_Paulo), status `scheduled|sending|sent|failed|canceled`, erro, `sent_message_ids`.
- Upload de mídia vai **direto ao domínio da API** (não pelo Vercel, que limita corpo a ~4.5 MB). Limite por arquivo: 2 GB (limite Telegram user), configurável; padrão 500 MB.
- Mídia em `/data/media/{user_id}/{uuid}`; apagada 7 dias após `sent` ou cancelamento.
- Validação ao agendar: conta tem permissão de postar no grupo.
- Envio: job `send_post` no `run_at`. Idempotência: status muda para `sending` na mesma transação que trava o job; se o processo cair em `sending`, não reenvia automaticamente — marca `failed` com "interrompido, verificar no grupo" (evita duplicado).
- "Postar agora" = `run_at = now()`.

### 7.8 Executor de jobs
- Tabela `jobs`: `type`, `payload`, `account_id`, `run_at`, `status (pending|running|done|failed)`, `attempts`, `last_error`.
- `FloodWaitError(s)` → reagenda para `now + s + 5`, sem contar tentativa. Outros erros transitórios → até 3 tentativas com backoff. Erro permanente → `failed`.
- Execução serializada por conta (lock asyncio por conta) para não disparar chamadas concorrentes da mesma conta.

## 8. Esquema do banco (resumo)

- `users` (id, email, password_hash argon2, role `admin|partner`, name, created_at, disabled)
- `tg_accounts` (id, owner_id→users, label, phone, api_id, api_hash_enc, session_enc, tg_user_id, display_name, status, dead_reason, last_seen_at, created_at)
- `channels` (id, owner_id, tg_chat_id, access_hash, title, username, kind, member_count, manager_account_id→tg_accounts, join_mode `auto|manual`, status, last_synced_at)
- `channel_admins` (channel_id, tg_user_id, name, rights jsonb, synced_at)
- `join_requests` (id, channel_id, tg_user_id, name, username, requested_at, status `pending|approved|rejected`, decided_by `auto|user`, decided_at)
- `scheduled_posts` (id, owner_id, account_id, channel_id, text, run_at, status, error, sent_message_ids, created_at)
- `post_media` (id, post_id, path, mime, size, position)
- `jobs` (ver 7.8)
- `action_logs` (id, owner_id, account_id, channel_id, action, target, result, detail, created_at)

Toda tabela de domínio tem `owner_id` (direto ou via FK); toda query de endpoint de parceiro filtra por ele.

## 9. Segurança

- Sessions e api_hash criptografados com Fernet; chave `DASH_ENCRYPTION_KEY` só no `.env` da VPS. Nunca retornados pela API, nunca logados.
- Login do painel: email + senha (argon2), cookie de sessão httpOnly, Secure, SameSite=Lax. Frontend e API em subdomínios do mesmo domínio (`painel.<dominio>` na Vercel, `api.<dominio>` na VPS) → cookie first-party com `Domain=.<dominio>`.
- CORS só para a origem do painel, com credentials. Proteção CSRF: header custom obrigatório em métodos de escrita + SameSite.
- Rate limit simples no login do painel (ex.: 10 tentativas/15 min por IP).
- Isolamento: dependência FastAPI `current_user`; helpers de query que exigem `owner_id`; admin passa por bypass explícito. Testes cobrindo acesso cruzado (deve dar 404).
- Postgres não exposto para fora do docker network.
- Backup diário `pg_dump` (cron no host, retenção 7 dias) — sessions criptografadas dentro, chave fora.

## 10. Frontend

- Next.js App Router + Tailwind, PT-BR, responsivo (uso no celular importa).
- Tema escuro: preto (`#0B0B0C` fundo, `#151517` superfícies), dourado (`#C9A54C` destaque/ações primárias), branco/off-white para texto; vermelho só para `dead`/erros, verde discreto para `online`.
- Telas:
  1. Login
  2. Visão geral: cards de contas (status), grupos (membros, pendentes), próximos posts, alertas de conta caída
  3. Contas: lista + "Conectar conta" (wizard número → código → 2FA) + importar session
  4. Grupos: lista; detalhe com abas **Resumo** (membros, admins, conta gestora, modo de entrada), **Solicitações** (toggle auto/manual, pendentes, aprovar todos), **Membros** (busca, remover/banir)
  5. Agenda: calendário/lista por dia, filtro por grupo/conta; criar/editar post (conta, grupo, texto, upload de mídia com preview, data/hora, "postar agora")
  6. Logs: action_logs filtráveis
  7. Admin (só admin): usuários (criar parceiro, desativar)

## 11. Deploy

- Repositório Git com `backend/`, `frontend/`, `deploy/` (`docker-compose.yml`, `.env.example`, `nginx/dashchannel.conf`), `README.md` com passo a passo na VPS.
- `docker compose up -d` sobe `app` + `postgres`; migrações Alembic rodam no start do app.
- Comando CLI para criar o primeiro admin (`python -m app.cli create-admin`).
- Frontend: projeto Vercel apontando para `frontend/`, env `NEXT_PUBLIC_API_URL`.

## 12. Testes

- Backend: pytest + Postgres de teste (docker); `TelegramGateway` fake. Cobrir: fluxo de login (com/sem 2FA, código errado), health check (erro fatal → dead sem retry), executor (FloodWait reagenda, idempotência de post), throttle de aprovação, isolamento entre usuários em todos os endpoints, criptografia (nada em claro no banco).
- Frontend: typecheck + lint + build; testes de componente só para o wizard de login e o formulário de post.

## 13. Deixado para quem constrói

Estrutura de pastas interna, nomes de módulos, componentes de UI, biblioteca de calendário, detalhes de paginação, intervalos exatos (desde que respeitem os limites acima).

## 14. Pendências com o dono

- Domínio para `painel.` / `api.`.
- Contrato da API do TData (para restauração automática; v1 funciona com importação manual).
- Remoto Git e acesso à VPS para deploy.
