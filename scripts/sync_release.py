import os
import shutil
from pathlib import Path

SRC_DIR = Path("j:/Mklan-Studio-ANTIGravity").resolve()
DST_DIR = SRC_DIR / "Mklan-AI-Github"

EXCLUDED_DIR_NAMES = {
    ".git",
    ".github",
    "venv",
    ".venv",
    "node_modules",
    "dist",
    ".pytest_cache",
    ".superpowers",
    "__pycache__",
    "postgres",
    "studio_postgres",
    "Mklan-AI-Github",  # Exclude target directory
}

EXCLUDED_FILES = {
    ".env",
    "backend_logs.txt",
    "recent_logs.txt",
    "scan_error.txt",
    "wildcards_500_error.txt",
}

def should_exclude(path: Path) -> bool:
    rel_path = path.relative_to(SRC_DIR)
    parts = rel_path.parts
    
    # Exclude root-level "services" folder
    if len(parts) > 0 and parts[0] == "services":
        return True
        
    # Exclude standard directory names
    for part in parts:
        if part in EXCLUDED_DIR_NAMES:
            return True
        if part.startswith("scan_traceback"):
            return True
        if part.startswith("refactor_") and part.endswith(".py"):
            return True
        if part.startswith("rename_") and part.endswith(".py"):
            return True
        if part.startswith("generate_") and part.endswith(".py"):
            return True
            
    # Exclude databases and temp logs
    if path.name in EXCLUDED_FILES:
        return True
    if path.suffix in {".db", ".sqlite", ".sqlite3"}:
        return True
    return False

def sync_directories():
    print(f"Syncing from {SRC_DIR} to {DST_DIR}...")
    
    folders_to_sync = ["backend", "frontend", "media-indexer", "plans", "scripts"]
    files_to_sync = ["docker-compose.yml", ".env.example", "README.md", "DOCUMENTATION.md", "CHANGELOG.md"]

    # Sync folders
    for folder in folders_to_sync:
        src_folder = SRC_DIR / folder
        dst_folder = DST_DIR / folder
        
        if not src_folder.exists():
            continue
            
        if dst_folder.exists():
            shutil.rmtree(dst_folder)
            
        for root, dirs, files in os.walk(src_folder):
            root_path = Path(root)
            if should_exclude(root_path):
                continue
                
            rel_path = root_path.relative_to(src_folder)
            target_dir = dst_folder / rel_path
            target_dir.mkdir(parents=True, exist_ok=True)
            
            for file in files:
                file_path = root_path / file
                if should_exclude(file_path):
                    continue
                shutil.copy2(file_path, target_dir / file)

    # Sync files
    for file in files_to_sync:
        src_file = SRC_DIR / file
        dst_file = DST_DIR / file
        if src_file.exists():
            shutil.copy2(src_file, dst_file)
            
    print("Sync complete.")

if __name__ == "__main__":
    sync_directories()
