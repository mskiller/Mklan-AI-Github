# Worker

The worker polls queued scan jobs from PostgreSQL and performs the indexing pipeline:

1. Walk approved source roots recursively
2. Detect supported image/video files
3. Upsert asset rows
4. Extract metadata with ExifTool and ffprobe
5. Normalize metadata and tags
6. Generate previews
7. Compute pHash and CLIP embeddings
8. Refresh similarity links

## Commands

```powershell
set PYTHONPATH=backend/src;worker/src
pip install -e ./worker
python -m media_indexer_worker.main
```

CLIP runs on CPU by default. The first enabled run downloads the configured model.

