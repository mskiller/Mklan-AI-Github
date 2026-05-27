# Mklan Studio V2 Phase 3 Expansion

## Delivered
- Native `/video` route and `/api/video/*` APIs for model inventory, settings, clips, jobs, and V2 job-backed generation.
- Mock video smoke path writes MP4 files and JSON sidecars to `data/generated/video/`, then registers them in the V2 asset registry with workspace scope.
- Existing Movie video providers are available through the shared provider settings: `mock`, `lightx2v`, and `wan_gguf`.
- Movie sequence video surfaces can open the native `/video` route prefilled with project, scene, sequence, and Wan prompt context.
- Florence-2 caption provider is available as `florence2`, with an optional `studio_florence` Docker profile service.
- Workspace ZIP packages are available at `/api/workspaces/{workspace_id}/export.zip` and `/api/workspaces/import`.
- Workflow summaries now include read-only ComfyUI edges, and the frontend node inspector is shared by Generation and Video.

## Local Smoke
```powershell
docker compose config --quiet
docker compose up -d --build backend studio_worker frontend
curl.exe -s http://localhost:8080/api/video/models
curl.exe -s http://localhost:8080/api/video/clips
```

Queue a mock video job:
```powershell
$body = @{ prompt = 'phase three docker smoke clip'; provider = 'mock'; duration_s = 1; fps = 12; width = 512; height = 288 } | ConvertTo-Json
$response = Invoke-RestMethod -Uri http://localhost:8080/api/video/generate -Method Post -ContentType 'application/json' -Body $body
Invoke-RestMethod -Uri "http://localhost:8080/api/jobs/$($response.job.id)"
```

Optional Florence sidecar:
```powershell
docker compose --profile florence up -d --build studio_florence
curl.exe -s http://localhost:8091/health
```

## Notes
- Florence model download remains opt-in through `STUDIO_FLORENCE_ALLOW_DOWNLOAD=true`.
- Workspace ZIP import creates a new workspace by default and does not mutate legacy Wildcards, Movie, or Cards SQLite stores.
- Real Wan/LightX2V runs still depend on local model files and GPU readiness; `mock` is the default deterministic smoke path.
