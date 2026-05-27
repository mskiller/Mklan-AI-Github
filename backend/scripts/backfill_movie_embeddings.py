import sys
from pathlib import Path
from sqlmodel import Session, select
from sentence_transformers import SentenceTransformer

# Add backend to path so we can import app
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.v2.core_db import studio_database_url
from sqlalchemy import create_engine
from app.v2.models_movie import MovieProject, MovieStoryScene, MovieStoryBeat, MovieScene

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
        # Process Projects
        count_stmt = select(MovieProject).where(MovieProject.embedding == None)
        total_proj = len(session.exec(count_stmt).all())
        print(f"Found {total_proj} projects without embeddings.")
        
        processed = 0
        while total_proj > 0:
            stmt = select(MovieProject).where(MovieProject.embedding == None).limit(BATCH_SIZE)
            entries = session.exec(stmt).all()
            if not entries: break
                
            texts = [f"{e.name}\n{e.scenario_text}\n{e.genre}\n{e.tone}\n{e.style_anchor_text}" for e in entries]
            embeddings = model.encode(texts)
            
            for entry, emb in zip(entries, embeddings):
                entry.embedding = emb.tolist()
                
            session.commit()
            processed += len(entries)
            print(f"Projects Progress: {processed}/{total_proj}")

        # Process Story Scenes
        count_stmt = select(MovieStoryScene).where(MovieStoryScene.embedding == None)
        total_story_scenes = len(session.exec(count_stmt).all())
        print(f"Found {total_story_scenes} story scenes without embeddings.")
        
        processed = 0
        while total_story_scenes > 0:
            stmt = select(MovieStoryScene).where(MovieStoryScene.embedding == None).limit(BATCH_SIZE)
            entries = session.exec(stmt).all()
            if not entries: break
                
            texts = [f"{e.title}\n{e.narrative_text}" for e in entries]
            embeddings = model.encode(texts)
            
            for entry, emb in zip(entries, embeddings):
                entry.embedding = emb.tolist()
                
            session.commit()
            processed += len(entries)
            print(f"Story Scenes Progress: {processed}/{total_story_scenes}")

        # Process Story Beats
        count_stmt = select(MovieStoryBeat).where(MovieStoryBeat.embedding == None)
        total_beats = len(session.exec(count_stmt).all())
        print(f"Found {total_beats} story beats without embeddings.")
        
        processed = 0
        while total_beats > 0:
            stmt = select(MovieStoryBeat).where(MovieStoryBeat.embedding == None).limit(BATCH_SIZE)
            entries = session.exec(stmt).all()
            if not entries: break
                
            texts = [f"{e.title}\n{e.summary_text}\n{e.purpose_text}" for e in entries]
            embeddings = model.encode(texts)
            
            for entry, emb in zip(entries, embeddings):
                entry.embedding = emb.tolist()
                
            session.commit()
            processed += len(entries)
            print(f"Story Beats Progress: {processed}/{total_beats}")

        # Process Scenes
        count_stmt = select(MovieScene).where(MovieScene.embedding == None)
        total_scenes = len(session.exec(count_stmt).all())
        print(f"Found {total_scenes} scenes without embeddings.")
        
        processed = 0
        while total_scenes > 0:
            stmt = select(MovieScene).where(MovieScene.embedding == None).limit(BATCH_SIZE)
            entries = session.exec(stmt).all()
            if not entries: break
                
            texts = [f"{e.title}\n{e.narrative_text}\n{e.prompt_text}\n{e.camera_direction}\n{e.action_direction}" for e in entries]
            embeddings = model.encode(texts)
            
            for entry, emb in zip(entries, embeddings):
                entry.embedding = emb.tolist()
                
            session.commit()
            processed += len(entries)
            print(f"Scenes Progress: {processed}/{total_scenes}")

if __name__ == "__main__":
    main()
