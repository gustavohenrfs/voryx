# Voryx

Painel para operar grupos de prévias no Telegram: conectar as contas das modelos, agendar posts por conta,
aprovar pedidos de entrada (automático ou manual), remover/banir membros e saber na hora quando uma conta cai.

- **Backend** (`backend/`): Python 3.12, FastAPI e Telethon (MTProto) num processo só, Postgres como banco e fila de jobs.
- **Frontend** (`frontend/`): Next.js na Vercel, em `painel.voryx.pro`.
- **API**: `api.voryx.pro` na VPS (`176.57.189.30`), atrás do nginx que já existe lá.
- Design e plano: `docs/superpowers/specs/` e `docs/superpowers/plans/`.

---

## Deploy na VPS (setup único)

Todos os comandos abaixo rodam **dentro de `/opt/voryx`**, a menos que esteja escrito outra coisa.

### 1. Usuário de deploy

O GitHub Actions entra na VPS com este usuário para atualizar o app. Rode como root:

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy            # atenção: grupo docker = acesso de root na prática
chown -R deploy:deploy /opt/voryx
```

Na **sua máquina**, gere a chave que o GitHub vai usar:

```bash
ssh-keygen -t ed25519 -f voryx_deploy -N "" -C "github-actions-voryx"
```

De volta na VPS, autorize a chave pública:

```bash
sudo -u deploy mkdir -p /home/deploy/.ssh
sudo -u deploy tee -a /home/deploy/.ssh/authorized_keys < voryx_deploy.pub   # cole o conteúdo do .pub
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
```

No GitHub, em **Settings → Secrets and variables → Actions**, crie:

| Secret | Valor |
|---|---|
| `VPS_HOST` | `176.57.189.30` |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | conteúdo inteiro do arquivo `voryx_deploy` (a chave **privada**) |

Depois apague o `voryx_deploy` da sua máquina ou guarde num cofre de senhas.

### 2. Clonar o repositório (deploy key só de leitura)

```bash
sudo -iu deploy
ssh-keygen -t ed25519 -f ~/.ssh/github_voryx -N "" -C "voryx-vps"
cat ~/.ssh/github_voryx.pub
```

Cole essa chave em **GitHub → repositório → Settings → Deploy keys → Add deploy key** (sem marcar "write access"). Depois:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_voryx
  IdentitiesOnly yes
EOF
cd /opt/voryx
git clone git@github.com:gustavohenrfs/voryx.git .
```

### 3. Configurar o `.env`

```bash
cd /opt/voryx
cp .env.example .env
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # → VORYX_ENCRYPTION_KEY
openssl rand -hex 32                                                                          # → VORYX_SECRET_KEY
nano .env      # preencha as chaves e troque a senha do Postgres (nos dois lugares)
chmod 600 .env
```

Se o `python3` da VPS não tiver `cryptography`, gere a chave depois do passo 4 com
`docker compose run --rm --no-deps app python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

> **Guarde uma cópia da `VORYX_ENCRYPTION_KEY` fora da VPS** (cofre de senhas). Ela criptografa as sessions do Telegram.
> Se ela se perder, todas as contas precisam ser conectadas de novo.

### 4. Subir o app

```bash
cd /opt/voryx
docker compose up -d --build
docker compose ps                         # app e postgres "healthy"
curl -s http://127.0.0.1:8001/health      # {"ok":true,...}
docker compose exec app python -m app.cli create-admin --email voce@exemplo.com --name "Seu nome"
```

O app escuta só em `127.0.0.1:8001`, então nada fica exposto sem passar pelo nginx. As migrações do banco rodam sozinhas a cada start.

### 5. Nginx e HTTPS (sem mexer no SaaS do X)

O Voryx usa **um arquivo de site separado**. Não edite `nginx.conf` nem os sites do X.

```bash
sudo cp /opt/voryx/deploy/nginx/voryx.conf /etc/nginx/sites-available/voryx.conf
sudo ln -s /etc/nginx/sites-available/voryx.conf /etc/nginx/sites-enabled/voryx.conf
sudo nginx -t                      # OBRIGATÓRIO: só siga se aparecer "syntax is ok" e "test is successful"
sudo systemctl reload nginx        # reload, nunca restart
sudo certbot --nginx -d api.voryx.pro
sudo nginx -t && sudo systemctl reload nginx
curl -s https://api.voryx.pro/health
```

> ⚠️ **Sempre rode `sudo nginx -t` antes de `sudo systemctl reload nginx`.** O nginx é compartilhado com o SaaS do X:
> se a config tiver erro e você recarregar mesmo assim, os dois saem do ar. Se o `nginx -t` falhar, não recarregue:
> corrija o arquivo ou remova o link (`sudo rm /etc/nginx/sites-enabled/voryx.conf`) e teste de novo.

O `certbot --nginx -d api.voryx.pro` mexe só no bloco desse domínio.

### 6. Frontend na Vercel

1. **Add New → Project**, importe `gustavohenrfs/voryx` e coloque **Root Directory** = `frontend`.
2. Em Environment Variables, crie `NEXT_PUBLIC_API_URL` = `https://api.voryx.pro`.
3. Faça o deploy e, em **Settings → Domains**, adicione `painel.voryx.pro`. O CNAME já foi criado na Hostinger.
4. Abra `https://painel.voryx.pro` e entre com o admin do passo 4.

O login usa um cookie no domínio `.voryx.pro`. Por isso o painel precisa estar em `painel.voryx.pro`: pelo domínio
`*.vercel.app` o login não funciona.

### 7. Backup diário do banco

```bash
mkdir -p /opt/voryx/backups
crontab -e   # como o usuário deploy; adicione a linha:
30 4 * * * cd /opt/voryx && docker compose exec -T postgres pg_dump -U voryx voryx | gzip > backups/voryx-$(date +\%F).sql.gz && find backups -name '*.sql.gz' -mtime +7 -delete
```

O backup tem as sessions criptografadas. A chave fica fora dele (no `.env`), então guarde as duas coisas.

Para restaurar: `gunzip -c backups/voryx-AAAA-MM-DD.sql.gz | docker compose exec -T postgres psql -U voryx voryx`.

---

## Deploy automático

- Todo push roda o **CI** (`.github/workflows/ci.yml`): testes do backend com Postgres real, checagem da migração,
  e lint, typecheck, testes e build do frontend.
- Um push na `main` com o CI verde roda o **Deploy** (`deploy.yml`): entra na VPS como `deploy` e executa
  `cd /opt/voryx && git pull --ff-only && docker compose up -d --build app`. Depois confere `https://api.voryx.pro/health`.
- Se o CI falhar, nada vai pra VPS.
- A Vercel publica o frontend sozinha a cada push.
- Cada deploy do backend reconecta as contas do Telegram em poucos segundos. Os jobs pendentes continuam no banco.
  Um post que estava no meio do envio vira "falhou: verificar no grupo" e não é reenviado, pra nunca sair duplicado.

## Operação

| Situação | O que fazer |
|---|---|
| Ver logs | `cd /opt/voryx && docker compose logs -f app` |
| Conta aparece como "Caiu" | No painel, em **Contas**: **Relogar** (api_id + api_hash + código) ou **Importar session** (StringSession do TData). O motivo aparece embaixo do nome. |
| Grupo com "Conta gestora caiu" | Troque a conta gestora no **Resumo** do grupo ou reconecte a conta. |
| "aguarde Ns" ao banir/aprovar | É limite do Telegram (FloodWait). Os jobs se reagendam sozinhos; ações manuais, tente depois do tempo indicado. |
| Reiniciar | `docker compose restart app` |
| Atualizar na mão | `cd /opt/voryx && git pull --ff-only && docker compose up -d --build app` |
| Criar outro admin | `docker compose exec app python -m app.cli create-admin --email ... --name ...` |
| Parceiros | Pelo painel, em **Usuários** (só admin): criar, trocar senha, desativar. |

Uso de memória: `app` tem limite de 1 GB e `postgres` de 512 MB (no `docker-compose.yml`).

## Desenvolvimento local

```bash
# backend
cd backend
pip install uv && uv venv --python 3.12 && uv pip install -e ".[dev]"
.venv/Scripts/python -m pytest -q          # Linux/mac: .venv/bin/python
# frontend
cd frontend && npm install && npm run dev
```

Por padrão, os testes do backend usam SQLite. Com `TEST_DATABASE_URL=postgresql+asyncpg://...` eles rodam no Postgres, como no CI.
