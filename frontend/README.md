# Front-end (React + Vite)

SPA servida pelo nginx em produção; em dev, `npm run dev` com proxy de `/api`
(sem o prefixo), `/socket.io` e `/images` para `localhost:3000`.

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # Vitest + Testing Library (jsdom)
npm run typecheck
npm run build
```

## Base comum (conferida no início da spec 004)

| Peça | Origem | Situação |
|---|---|---|
| `src/api/client.ts` (`/api`, `ApiError` tipado) | 002 | ok |
| `src/auth/AuthContext.tsx`, `RequireRole.tsx` | 002 | ok |
| `src/layout/Layout.tsx`, `src/styles.css` (cores em variáveis) | 002 | ok |
| `src/lib/money.ts` (`formatBRL`, `parseBRLToCents`) | 002 | ok — o `parseBRLToCents` que a 004 previa criar já existe |
| `src/lib/clock.ts`, `src/lib/socket.ts` | 003 | ok |
| `src/theme/ThemeProvider.tsx` vazio | 003 (T006b) | ok |
| rotas `/carteira`, `/arremates`, `/auditoria/:id`, `/comprovante/:id` | 003 (T006b) | ok, com página provisória |
| Vitest, Testing Library e jsdom | 002 | ok |

Nenhuma peça faltou; a 004 só estende.

## Organização

- `pages/` e `pages/auctioneer/`: login, cadastro e painel do leiloeiro (002).
- `features/lots`, `features/vitrine`, `features/sala`: vitrine e sala ao vivo (003).
- `audit/`, `wallet/`, `participations/`, `receipt/`, `theme/`: área do licitante,
  comprovante, auditoria pública e tema (004).
