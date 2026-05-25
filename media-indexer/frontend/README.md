# Frontend

Next.js App Router frontend for the media indexer MVP.

## Pages

- `/` dashboard
- `/login`
- `/sources`
- `/scan-jobs`
- `/search`
- `/assets/[id]`
- `/assets/[id]/similar`
- `/compare?a=...&b=...`

## Commands

```powershell
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` so the browser can reach the FastAPI service.

