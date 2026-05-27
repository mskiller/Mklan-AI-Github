import React, { useEffect, useState } from 'react';
import { Trash2, FolderOpen, RefreshCw, Layers, Crop as CropIcon } from 'lucide-react';

export interface GalleryImage {
  id?: string;
  name: string;
  size: number;
  created_at: number;
  url: string;
  metadata?: any;
}

interface MediaCollection {
  id: string;
  name: string;
  asset_count: number;
}

interface Props {
  characterName: string;
  activeCollectionId: string | null;
  onCollectionSelect: (id: string | null) => void;
  onReopenAsset: (imgUrl: string) => void;
}

export function CharacterAssetGallery({ characterName, activeCollectionId, onCollectionSelect, onReopenAsset }: Props) {
  const [collections, setCollections] = useState<MediaCollection[]>([]);
  const [assets, setAssets] = useState<GalleryImage[]>([]);
  const [loading, setLoading] = useState(false);
  const [showNewCollection, setShowNewCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState(`Character - ${characterName || 'Unnamed'}`);

  const fetchCollections = async () => {
    try {
      const res = await fetch("/api/media/collections");
      if (res.ok) {
        const data = await res.json();
        setCollections(Array.isArray(data) ? data : (data.collections || []));
      }
    } catch (e) {
      console.error("Failed to fetch collections", e);
    }
  };

  const fetchAssets = async () => {
    if (!activeCollectionId) {
      setAssets([]);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/media/collections/${activeCollectionId}?page_size=100`);
      if (res.ok) {
        const data = await res.json();
        const items = data.assets || data.items || [];
        const galleryImages = items.map((item: any) => ({
          id: item.id,
          name: item.filename || 'asset',
          size: item.size_bytes || 0,
          created_at: new Date(item.created_at || item.modified_at || Date.now()).getTime(),
          url: `/api/media/assets/${item.id}/image?w=1024`,
          metadata: item.normalized_metadata || {}
        }));
        setAssets(galleryImages);
      }
    } catch (e) {
      console.error("Failed to fetch assets", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCollections();
  }, []);

  useEffect(() => {
    fetchAssets();
  }, [activeCollectionId]);

  const handleCreateCollection = async () => {
    try {
      const res = await fetch("/api/media/collections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newCollectionName })
      });
      if (res.ok) {
        const data = await res.json();
        await fetchCollections();
        onCollectionSelect(data.id);
        setShowNewCollection(false);
      }
    } catch (e) {
      console.error("Failed to create collection", e);
    }
  };

  const handleDeleteAsset = async (assetId: string) => {
    if (!activeCollectionId || !assetId) return;
    try {
      // Remove from collection
      await fetch(`/api/media/collections/${activeCollectionId}/assets`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_ids: [assetId] })
      });
      setAssets(prev => prev.filter(a => a.id !== assetId));
    } catch (e) {
      console.error("Failed to remove asset from collection", e);
    }
  };

  return (
    <div style={{ marginTop: '2rem', padding: '1rem', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h3 style={{ margin: 0, fontSize: '1.1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Layers size={18} /> Asset Gallery
        </h3>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <select 
            value={activeCollectionId || ''} 
            onChange={(e) => onCollectionSelect(e.target.value || null)}
            style={{ padding: '0.4rem', borderRadius: '4px', background: 'var(--bg-main)', color: 'white', border: '1px solid var(--border-color)' }}
          >
            <option value="">-- Select Collection --</option>
            {collections.map(c => (
              <option key={c.id} value={c.id}>{c.name} ({c.asset_count})</option>
            ))}
          </select>
          <button 
            onClick={() => setShowNewCollection(!showNewCollection)}
            style={{ padding: '0.4rem 0.8rem', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '4px', cursor: 'pointer' }}
          >
            New
          </button>
          <button 
            onClick={fetchAssets}
            disabled={!activeCollectionId || loading}
            style={{ padding: '0.4rem', background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
            title="Refresh Assets"
          >
            <RefreshCw size={16} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      {showNewCollection && (
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', padding: '0.5rem', background: 'var(--bg-main)', borderRadius: '4px' }}>
          <input 
            type="text" 
            value={newCollectionName} 
            onChange={e => setNewCollectionName(e.target.value)}
            style={{ flex: 1, padding: '0.4rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.05)', color: 'white' }}
          />
          <button 
            onClick={handleCreateCollection}
            style={{ padding: '0.4rem 1rem', background: 'linear-gradient(135deg, var(--accent), #5a4bcf)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            Create
          </button>
        </div>
      )}

      {!activeCollectionId ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <FolderOpen size={32} style={{ opacity: 0.5, marginBottom: '0.5rem' }} />
          <p>Select or create a collection to save and browse generated assets.</p>
        </div>
      ) : assets.length === 0 ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <p>No assets in this collection. Generated images will appear here.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '1rem', maxHeight: '400px', overflowY: 'auto', paddingRight: '0.5rem' }}>
          {assets.map(asset => (
            <div key={asset.id} style={{ position: 'relative', borderRadius: '6px', overflow: 'hidden', backgroundColor: '#111', aspectRatio: '1/1', border: '1px solid var(--border-color)' }}>
              <img 
                src={asset.url} 
                alt={asset.name} 
                style={{ width: '100%', height: '100%', objectFit: 'contain', cursor: 'pointer' }} 
                onClick={() => onReopenAsset(asset.url)}
                title="Click to reopen in Cropper"
              />
              <div style={{ position: 'absolute', bottom: '0', left: '0', right: '0', padding: '4px', background: 'rgba(0,0,0,0.7)', display: 'flex', justifyContent: 'center' }}>
                <button 
                  onClick={() => onReopenAsset(asset.url)}
                  style={{ display: 'flex', alignItems: 'center', gap: '4px', background: 'transparent', border: 'none', color: '#fff', fontSize: '0.75rem', cursor: 'pointer' }}
                >
                  <CropIcon size={12} /> Load into Cropper
                </button>
              </div>
              <button 
                onClick={(e) => { e.stopPropagation(); asset.id && handleDeleteAsset(asset.id); }}
                style={{ position: 'absolute', top: '4px', right: '4px', padding: '4px', background: 'rgba(0,0,0,0.6)', border: 'none', color: '#ff4444', borderRadius: '4px', cursor: 'pointer' }}
                title="Remove from Collection"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
