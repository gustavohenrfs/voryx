# Voryx — painel (Next.js)

## Decisões visuais

- **Cores** (tokens em `src/app/globals.css`): carvão `#0F0E0C` de fundo, superfície `#1A1816`, linhas `#2E2A25`,
  dourado `#C9A54C` para ação principal e destaque, texto off-white `#F3EFE6`, apagado `#9A9286`.
  Vermelho `#E2574C` só para conta caída / erro; verde `#6FBF8E` só para online/enviado.
- **Tipografia**: Fraunces (serifada, títulos e marca) + Manrope (interface). Sem caixa-alta em rótulos.
- **Elemento marcante**: a faixa de contas na Visão geral — cada modelo é um anel cuja cor é o status da conta.
  O resto é contido: listas em linhas, poucos cartões, nada de sombras decorativas.
- **Layout**: barra lateral no desktop, barra inferior no celular. Conteúdo alinhado à esquerda, largura máx. 5xl.

## Desenvolvimento

```bash
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev
```

Verificação: `npm run lint && npm run typecheck && npm test && npm run build`.

Deploy: projeto na Vercel com root `frontend/`, env `NEXT_PUBLIC_API_URL=https://api.voryx.pro`, domínio `painel.voryx.pro`.
