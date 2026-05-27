import sys
from pathlib import Path
from sqlmodel import Session, select
from sentence_transformers import SentenceTransformer

# Add backend to path so we can import app
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.v2.core_db import studio_database_url
from sqlalchemy import create_engine
from app.v2.models_cards import CardCharacter, CardLoreEntry, CardProject

BATCH_SIZE = 50

def get_engine():
    pg_url = studio_database_url()
    if pg_url and pg_url.startswith("postgresql://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(pg_url)

def main():
    print("Loading sentence-transformers model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    print("Model loaded successfully.")
    
    engine = get_engine()
    with Session(engine) as session:
        # Process Characters
        count_stmt = select(CardCharacter).where(CardCharacter.embedding == None)
        total_chars = len(session.exec(count_stmt).all())
        print(f"Found {total_chars} characters without embeddings.")
        
        processed = 0
        while total_chars > 0:
            stmt = select(CardCharacter).where(CardCharacter.embedding == None).limit(BATCH_SIZE)
            entries = session.exec(stmt).all()
            if not entries: break
                
            texts = [f"{e.name}\n{e.description}\n{e.personality}\n{e.scenario}\n{e.system_prompt}\n{e.appearance_summary}" for e in entries]
            embeddings = model.encode(texts)
            
            for entry, emb in zip(entries, embeddings):
                entry.embedding = emb.tolist()
                
            session.commit()
            processed += len(entries)
            print(f"Characters Progress: {processed}/{total_chars}")

        # Process Lore Entries
        count_stmt = select(CardLoreEntry).where(CardLoreEntry.embedding == None)
        total_lore = len(session.exec(count_stmt).all())
        print(f"Found {total_lore} lore entries without embeddings.")
        
        processed = 0
        while total_lore > 0:
            stmt = select(CardLoreEntry).where(CardLoreEntry.embedding == None).limit(BATCH_SIZE)
            entries = session.exec(stmt).all()
            if not entries: break
                
            texts = [f"{e.name}\n{e.keys_json}\n{e.content}" for e in entries]
            embeddings = model.encode(texts)
            
            for entry, emb in zip(entries, embeddings):
                entry.embedding = emb.tolist()
                
            session.commit()
            processed += len(entries)
            print(f"Lore Progress: {processed}/{total_lore}")

        # Process Projects
        count_stmt = select(CardProject).where(CardProject.embedding == None)
        total_proj = len(session.exec(count_stmt).all())
        print(f"Found {total_proj} projects without embeddings.")
        
        processed = 0
        while total_proj > 0:
            stmt = select(CardProject).where(CardProject.embedding == None).limit(BATCH_SIZE)
            entries = session.exec(stmt).all()
            if not entries: break
                
            texts = [f"{e.name}\n{e.seed_sentence}\n{e.scenario_text}" for e in entries]
            embeddings = model.encode(texts)
            
            for entry, emb in zip(entries, embeddings):
                entry.embedding = emb.tolist()
                
            session.commit()
            processed += len(entries)
            print(f"Projects Progress: {processed}/{total_proj}")

if __name__ == "__main__":
    main()
