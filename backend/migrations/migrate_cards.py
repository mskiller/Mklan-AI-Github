import sqlite3
import logging
import sys
from pathlib import Path
from sqlmodel import Session, SQLModel, text
from sqlalchemy import create_engine

# Add backend to sys.path so we can import from app
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.v2.core_db import studio_database_url
from app.v2.models_cards import (
    CardProject,
    CardCharacter,
    CardLoreEntry,
    CardUserProfile,
    CardGenerationRun,
    CardAppSetting,
    CardImageCandidate,
    CardSharedCharacterVault,
    CardSharedLoreVault,
    CardCompatibilityReport,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    sqlite_db_path = "data/cards/card_creator.db"
    if not Path(sqlite_db_path).exists():
        logger.error(f"SQLite database not found at {sqlite_db_path}")
        return

    pg_url = studio_database_url()
    if not pg_url:
        logger.error("STUDIO_DATABASE_URL not set")
        return
        
    if pg_url.startswith("postgresql://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+psycopg://", 1)
    
    logger.info(f"Connecting to PostgreSQL at {pg_url}")
    pg_engine = create_engine(pg_url)
    SQLModel.metadata.create_all(pg_engine)
    
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    tables = {
        "projects": CardProject,
        "characters": CardCharacter,
        "lore_entries": CardLoreEntry,
        "user_profiles": CardUserProfile,
        "generation_runs": CardGenerationRun,
        "app_settings": CardAppSetting,
        "image_candidates": CardImageCandidate,
        "shared_character_vault": CardSharedCharacterVault,
        "shared_lore_vault": CardSharedLoreVault,
        "compatibility_reports": CardCompatibilityReport,
    }

    with Session(pg_engine) as session:
        for table_name, model_cls in tables.items():
            logger.info(f"Migrating {table_name}...")
            sqlite_cursor.execute(f"SELECT * FROM {table_name}")
            batch = []
            for row in sqlite_cursor:
                data = dict(row)
                data["workspace_id"] = "default"
                obj = model_cls(**data)
                batch.append(obj)
                if len(batch) >= 1000:
                    session.add_all(batch)
                    session.commit()
                    batch.clear()
            if batch:
                session.add_all(batch)
                session.commit()
                
    logger.info("Migration successfully completed!")
    sqlite_conn.close()

if __name__ == "__main__":
    migrate()
