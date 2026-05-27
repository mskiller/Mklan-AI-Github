import sys
from pathlib import Path
from sqlmodel import Session, select
from sentence_transformers import SentenceTransformer

# Add backend to path so we can import app
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.v2.core_db import studio_database_url
from sqlalchemy import create_engine
from app.v2.models_wildcards import WildcardEntry

BATCH_SIZE = 500

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
        # Check how many entries need embeddings
        count_stmt = select(WildcardEntry).where(WildcardEntry.embedding == None)
        total_missing = len(session.exec(count_stmt).all())
        print(f"Found {total_missing} entries without embeddings.")
        
        if total_missing == 0:
            return
            
        processed = 0
        while True:
            # Fetch a batch
            stmt = select(WildcardEntry).where(WildcardEntry.embedding == None).limit(BATCH_SIZE)
            entries = session.exec(stmt).all()
            
            if not entries:
                break
                
            texts = [entry.normalized_text for entry in entries]
            print(f"Computing embeddings for batch of {len(texts)}...")
            
            embeddings = model.encode(texts)
            
            for entry, emb in zip(entries, embeddings):
                entry.embedding = emb.tolist()
                
            session.commit()
            processed += len(entries)
            print(f"Progress: {processed}/{total_missing} ({processed/total_missing*100:.1f}%)")

if __name__ == "__main__":
    main()
