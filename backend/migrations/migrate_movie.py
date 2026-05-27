import sqlite3
import logging
import sys
from pathlib import Path
from sqlmodel import Session, SQLModel
from sqlalchemy import create_engine

# Add backend to sys.path so we can import from app
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.v2.core_db import studio_database_url
from app.v2.models_movie import (
    MovieProject,
    MovieStoryScene,
    MovieStoryBeat,
    MovieScene,
    MovieSceneImageVariant,
    MovieSequenceVideoVariant,
    MovieClipAsset,
    MovieJob,
    MovieContinuityReview,
    MovieExportAsset,
    MovieProjectCharacter,
    MovieAppSetting,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    sqlite_db_path = "data/movie/movie_tool.db"
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
        "projects": MovieProject,
        "story_scenes": MovieStoryScene,
        "story_beats": MovieStoryBeat,
        "scenes": MovieScene,
        "scene_image_variants": MovieSceneImageVariant,
        "sequence_video_variants": MovieSequenceVideoVariant,
        "clip_assets": MovieClipAsset,
        "jobs": MovieJob,
        "continuity_reviews": MovieContinuityReview,
        "export_assets": MovieExportAsset,
        "project_characters": MovieProjectCharacter,
        "app_settings": MovieAppSetting,
    }

    with Session(pg_engine) as session:
        for table_name, model_cls in tables.items():
            logger.info(f"Migrating {table_name}...")
            try:
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
            except sqlite3.OperationalError as e:
                logger.warning(f"Failed to fetch {table_name}: {e}")
                
    logger.info("Migration successfully completed!")
    sqlite_conn.close()

if __name__ == "__main__":
    migrate()
