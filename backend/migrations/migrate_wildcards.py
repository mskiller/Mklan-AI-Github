import os
import sqlite3
import json
import logging
from pathlib import Path
import sys

# Add backend dir to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel

from app.v2.core_db import studio_database_url, normalize_database_url
from app.v2.models_wildcards import (
    WildcardSourceFile,
    WildcardEntry,
    WildcardEntryHistory,
    WildcardScanRun,
    WildcardTagIndex,
    WildcardCategoryIndex,
    WildcardCategoryStat,
    WildcardPromptModeIndex,
    WildcardPromptRecipe,
    WildcardTagOverride,
    WildcardTaxonomyRule,
    WildcardTaxonomyMeta,
    WildcardSourceFileStat,
    WildcardLlmJob,
    WildcardTagPolarityIndex,
)
from app.wildcards.config import WILDCARD_DB

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def load_json_field(row, field_name, default):
    val = row[field_name]
    if not val:
        return default
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        return default

def migrate():
    sqlite_db_path = WILDCARD_DB
    if not sqlite_db_path.exists():
        fallback_path = backend_dir.parent / "data" / "wildcards" / "wildcards.sqlite"
        if fallback_path.exists():
            sqlite_db_path = fallback_path
        else:
            logger.error(f"SQLite DB not found at {sqlite_db_path} or {fallback_path}")
            return

    logger.info(f"Connecting to SQLite DB at {sqlite_db_path}")
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    pg_url = studio_database_url()
    if pg_url and pg_url.startswith("postgresql://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not pg_url:
        logger.error("STUDIO_DATABASE_URL environment variable is not set. Cannot connect to Postgres.")
        return

    logger.info(f"Connecting to PostgreSQL at {pg_url}")
    pg_engine = create_engine(pg_url)

    logger.info("Creating tables if they don't exist in PostgreSQL...")
    SQLModel.metadata.create_all(pg_engine)

    with Session(pg_engine) as session:
        # source_files -> WildcardSourceFile
        logger.info("Migrating source_files...")
        sqlite_cursor.execute("SELECT * FROM source_files")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardSourceFile(
                id=row["id"],
                original_path=row["original_path"],
                relative_path=row["relative_path"],
                extension=row["extension"],
                size_bytes=row["size_bytes"],
                sha256=row["sha256"],
                last_modified=row["last_modified"],
                wildcard_path=row["wildcard_path"],
                import_status=row["import_status"],
                warning_count=row["warning_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # entries -> WildcardEntry
        logger.info("Migrating entries...")
        sqlite_cursor.execute("SELECT * FROM entries")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardEntry(
                id=row["id"],
                source_file_id=row["source_file_id"],
                wildcard_path=row["wildcard_path"],
                item_index=row["item_index"],
                raw_text=row["raw_text"],
                staged_text=row["staged_text"],
                normalized_text=row["normalized_text"],
                kind=row["kind"],
                prompt_mode=row["prompt_mode"],
                tags_json=load_json_field(row, "tags_json", {}),
                positive_tags_json=load_json_field(row, "positive_tags_json", []),
                negative_tags_json=load_json_field(row, "negative_tags_json", []),
                all_extracted_tags_json=load_json_field(row, "all_extracted_tags_json", []),
                prompt_parts_json=load_json_field(row, "prompt_parts_json", {}),
                tag_categories_json=load_json_field(row, "tag_categories_json", []),
                refs_json=load_json_field(row, "refs_json", {}),
                warnings_json=load_json_field(row, "warnings_json", {}),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # entry_history -> WildcardEntryHistory
        logger.info("Migrating entry_history...")
        sqlite_cursor.execute("SELECT * FROM entry_history")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardEntryHistory(
                id=row["id"],
                entry_id=row["entry_id"],
                previous_text=row["previous_text"],
                next_text=row["next_text"],
                created_at=row["created_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # scan_runs -> WildcardScanRun
        logger.info("Migrating scan_runs...")
        sqlite_cursor.execute("SELECT * FROM scan_runs")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardScanRun(
                id=row["id"],
                source_root=row["source_root"],
                summary_json=load_json_field(row, "summary_json", {}),
                created_at=row["created_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # tag_index -> WildcardTagIndex
        logger.info("Migrating tag_index...")
        sqlite_cursor.execute("SELECT * FROM tag_index")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardTagIndex(
                tag=row["tag"],
                category=row["category"],
                usage_count=row["usage_count"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # category_index -> WildcardCategoryIndex
        logger.info("Migrating category_index...")
        sqlite_cursor.execute("SELECT * FROM category_index")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardCategoryIndex(
                category=row["category"],
                usage_count=row["usage_count"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # category_stats -> WildcardCategoryStat
        logger.info("Migrating category_stats...")
        sqlite_cursor.execute("SELECT * FROM category_stats")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardCategoryStat(
                category=row["category"],
                entry_count=row["entry_count"],
                file_count=row["file_count"],
                tag_count=row["tag_count"],
                wildcard_count=row["wildcard_count"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # prompt_mode_index -> WildcardPromptModeIndex
        logger.info("Migrating prompt_mode_index...")
        sqlite_cursor.execute("SELECT * FROM prompt_mode_index")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardPromptModeIndex(
                prompt_mode=row["prompt_mode"],
                entry_count=row["entry_count"],
                file_count=row["file_count"],
                wildcard_count=row["wildcard_count"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # prompt_recipes -> WildcardPromptRecipe
        logger.info("Migrating prompt_recipes...")
        sqlite_cursor.execute("SELECT * FROM prompt_recipes")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardPromptRecipe(
                id=row["id"],
                name=row["name"],
                preset=row["preset"],
                slots_json=load_json_field(row, "slots_json", {}),
                negative_tags_json=load_json_field(row, "negative_tags_json", []),
                wildcard_refs_json=load_json_field(row, "wildcard_refs_json", {}),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # tag_overrides -> WildcardTagOverride
        logger.info("Migrating tag_overrides...")
        sqlite_cursor.execute("SELECT * FROM tag_overrides")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardTagOverride(
                tag=row["tag"],
                canonical_tag=row["canonical_tag"],
                category=row["category"],
                is_ignored=row["is_ignored"],
                updated_at=row["updated_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # taxonomy_rules -> WildcardTaxonomyRule
        logger.info("Migrating taxonomy_rules...")
        sqlite_cursor.execute("SELECT * FROM taxonomy_rules")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardTaxonomyRule(
                category=row["category"],
                keyword=row["keyword"],
                enabled=row["enabled"],
                updated_at=row["updated_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # taxonomy_meta -> WildcardTaxonomyMeta
        logger.info("Migrating taxonomy_meta...")
        sqlite_cursor.execute("SELECT * FROM taxonomy_meta")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardTaxonomyMeta(
                key=row["key"],
                value=row["value"],
                updated_at=row["updated_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # source_file_stats -> WildcardSourceFileStat
        logger.info("Migrating source_file_stats...")
        sqlite_cursor.execute("SELECT * FROM source_file_stats")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardSourceFileStat(
                source_file_id=row["source_file_id"],
                entry_count=row["entry_count"],
                prompt_count=row["prompt_count"],
                duplicate_count=row["duplicate_count"],
                unresolved_refs=row["unresolved_refs"],
                categories_json=load_json_field(row, "categories_json", []),
                prompt_modes_json=load_json_field(row, "prompt_modes_json", {}),
                updated_at=row["updated_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # llm_jobs -> WildcardLlmJob
        logger.info("Migrating llm_jobs...")
        sqlite_cursor.execute("SELECT * FROM llm_jobs")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardLlmJob(
                id=row["id"],
                task=row["task"],
                prompt_mode=row["prompt_mode"],
                endpoint=row["endpoint"],
                model=row["model"],
                input_text=row["input_text"],
                status=row["status"],
                suggestion=row["suggestion"],
                error=row["error"],
                endpoint_used=row["endpoint_used"],
                raw_json=row["raw_json"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                accepted_at=row["accepted_at"],
                rejected_at=row["rejected_at"],
                cancelled_at=row["cancelled_at"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        # tag_polarity_index -> WildcardTagPolarityIndex
        logger.info("Migrating tag_polarity_index...")
        sqlite_cursor.execute("SELECT * FROM tag_polarity_index")
        batch = []
        for row in sqlite_cursor:
            obj = WildcardTagPolarityIndex(
                tag=row["tag"],
                category=row["category"],
                polarity=row["polarity"],
                usage_count=row["usage_count"],
                workspace_id="default",
            )
            batch.append(obj)
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()

        logger.info("Updating sequences for auto-increment fields...")
        tables_with_id = [
            "wildcard_source_files",
            "wildcard_entries",
            "wildcard_entry_history",
            "wildcard_scan_runs",
            "wildcard_prompt_recipes",
            "wildcard_llm_jobs"
        ]
        
        for table in tables_with_id:
            try:
                # setval to max id or 1 if empty
                session.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table};"))
                session.commit()
            except Exception as e:
                logger.warning(f"Could not update sequence for {table}: {e}")
                session.rollback()

    logger.info("Migration successfully completed!")
    sqlite_conn.close()

if __name__ == '__main__':
    migrate()
