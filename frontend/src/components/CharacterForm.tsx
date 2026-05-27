import React, { useState, useEffect } from 'react';
import { CharacterData, parseCreatorNotes, serializeCreatorNotes } from '../hooks/useCharacterSheet';
import { listProjects, listCharacters, createCharacter, updateCharacter } from '../pages/cards/api';
import { ProjectListItem, Character, CharacterCreateRequest } from '../pages/cards/types';

interface Props {
  data: CharacterData;
  updateData: (updates: Partial<CharacterData>) => void;
  addSlot: (label: string, aspect?: number) => void;
  removeSlot: (slotId: string) => void;
  linkCharacter: (projectId: string | null, characterId: string | null) => void;
  resetToDefault: () => void;
}

const API_BASE = import.meta.env.VITE_CARDS_API_BASE_URL ?? "/cards";

function resolveAssetUrl(projectId: string, path: string): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('data:')) {
    return path;
  }
  const cleanPath = path.replace(/^\/+/, '');
  return `${API_BASE}/assets/${projectId}/${cleanPath}`;
}

async function dataURLtoBlob(dataUrl: string): Promise<Blob> {
  const res = await fetch(dataUrl);
  return await res.blob();
}

async function uploadAsset(projectId: string, assetPath: string, blob: Blob) {
  const formData = new FormData();
  formData.append("asset_path", assetPath);
  formData.append("file", blob, assetPath.split('/').pop());

  const response = await fetch(`${API_BASE}/projects/${projectId}/assets/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Upload failed: ${errorText}`);
  }

  return await response.json();
}

// Icons (SVG Components)
const TrashIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <polyline points="3 6 5 6 21 6"></polyline>
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
    <line x1="10" y1="11" x2="10" y2="17"></line>
    <line x1="14" y1="11" x2="14" y2="17"></line>
  </svg>
);

const PlusIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <line x1="12" y1="5" x2="12" y2="19"></line>
    <line x1="5" y1="12" x2="19" y2="12"></line>
  </svg>
);

const SyncIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
  </svg>
);

const DownloadIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
    <polyline points="7 10 12 15 17 10"></polyline>
    <line x1="12" y1="15" x2="12" y2="3"></line>
  </svg>
);

const ResetIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
    <polyline points="3 3 3 8 8 8"></polyline>
  </svg>
);

const LockIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
  </svg>
);

export function CharacterForm({ data, updateData, addSlot, removeSlot, linkCharacter, resetToDefault }: Props) {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [loadingCharacters, setLoadingCharacters] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [statusType, setStatusType] = useState<'info' | 'success' | 'error' | null>(null);
  // Slots manager fields
  const [newSlotLabel, setNewSlotLabel] = useState('');
  const [newSlotAspect, setNewSlotAspect] = useState<string>('free'); // '1', '0.75', 'free'
  const [exporting, setExporting] = useState(false);
  const [customTemplates, setCustomTemplates] = useState<any[]>([]);

  useEffect(() => {
    const raw = localStorage.getItem('mklan_custom_templates');
    if (raw) {
      try {
        setCustomTemplates(JSON.parse(raw));
      } catch (_) {}
    }
  }, [data.templateId]);
  // Load projects list
  useEffect(() => {
    let active = true;
    async function loadProjects() {
      setLoadingProjects(true);
      try {
        const list = await listProjects("active");
        if (active) {
          setProjects(list || []);
        }
      } catch (err) {
        if (active) {
          console.error("Failed to load cards projects:", err);
        }
      } finally {
        if (active) {
          setLoadingProjects(false);
        }
      }
    }
    loadProjects();
    return () => {
      active = false;
    };
  }, []);

  // Load characters list when linked project changes
  useEffect(() => {
    if (!data.linkedProjectId) {
      setCharacters([]);
      return;
    }
    let active = true;
    async function loadCharacters() {
      setLoadingCharacters(true);
      try {
        const list = await listCharacters(data.linkedProjectId!);
        if (active) {
          setCharacters(list || []);
        }
      } catch (err) {
        if (active) {
          console.error("Failed to load cards characters:", err);
        }
      } finally {
        if (active) {
          setLoadingCharacters(false);
        }
      }
    }
    loadCharacters();
    return () => {
      active = false;
    };
  }, [data.linkedProjectId]);

  const buildCreateRequest = (data: CharacterData): CharacterCreateRequest => ({
    name: data.name || "Unnamed Character",
    description: data.role || "",
    personality: data.bio || "",
    scenario: "",
    first_message: "",
    example_dialogue: "",
    tags: [],
    creator_notes: "",
    system_prompt: "",
    post_history_instructions: "",
    alternate_greetings: [],
    creator: "",
    character_version: "1.0",
    character_note: "",
    character_note_depth: 4,
    character_note_role: "system" as const,
    talkativeness: null,
    appearance_summary: "",
    booru_character_name: "",
    booru_copyright: ""
  });

  const handleImport = async () => {
    if (!data.linkedProjectId || !data.linkedCharacterId) {
      setStatusMessage("Select a project and character card first.");
      setStatusType("error");
      return;
    }
    const character = characters.find(c => c.id === data.linkedCharacterId);
    if (!character) {
      setStatusMessage("Selected character card not found.");
      setStatusType("error");
      return;
    }

    try {
      setStatusMessage("Importing character card...");
      setStatusType("info");

      const parsed = parseCreatorNotes(character.creator_notes);

      // Construct the imported state updates
      const updates: Partial<CharacterData> = {
        name: character.name || '',
        role: character.description || '',
        bio: character.personality || '',
      };

      // Default slot images mapping
      const importedImages: Record<string, string> = {};
      if (character.avatar_url) {
        importedImages['face'] = character.avatar_url;
      }
      if (character.portrait_url) {
        importedImages['profile'] = character.portrait_url;
      }
      if (character.fullbody_shot_url) {
        importedImages['full-body'] = character.fullbody_shot_url;
      }

      if (parsed) {
        if (parsed.hp !== undefined) updates.hp = parsed.hp;
        if (parsed.energy !== undefined) updates.energy = parsed.energy;
        if (parsed.combat !== undefined) updates.combat = parsed.combat;
        if (parsed.intellect !== undefined) updates.intellect = parsed.intellect;
        if (parsed.agility !== undefined) updates.agility = parsed.agility;
        if (parsed.templateId !== undefined) updates.templateId = parsed.templateId;
        if (parsed.orientation !== undefined) updates.orientation = parsed.orientation;
        if (parsed.bio !== undefined) updates.bio = parsed.bio;
        if (parsed.role !== undefined) updates.role = parsed.role;
        
        // Restore slots
        if (Array.isArray(parsed.slots)) {
          updates.slots = parsed.slots;
        }

        // Restore custom slot images
        if (parsed.images) {
          Object.entries(parsed.images).forEach(([slotId, imageSrc]) => {
            if (imageSrc && typeof imageSrc === 'string') {
              importedImages[slotId] = resolveAssetUrl(data.linkedProjectId!, imageSrc);
            }
          });
        }
      }

      updates.images = importedImages;
      updateData(updates);

      setStatusMessage("Character card imported successfully!");
      setStatusType("success");
    } catch (err: any) {
      console.error("Import failed:", err);
      setStatusMessage(`Import failed: ${err.message || err}`);
      setStatusType("error");
    }
  };

  const handleExport = async () => {
    if (!data.linkedProjectId) {
      setStatusMessage("Select a project first.");
      setStatusType("error");
      return;
    }

    setExporting(true);
    setStatusMessage("Exporting character data...");
    setStatusType("info");

    try {
      let characterId = data.linkedCharacterId;
      let isNew = false;

      // 1. Create a character card in the project if one doesn't exist yet
      if (!characterId || characterId === 'CREATE_NEW') {
        setStatusMessage("Creating character card...");
        const createPayload = buildCreateRequest(data);
        const newChar = await createCharacter(data.linkedProjectId, createPayload);
        characterId = newChar.id;
        linkCharacter(data.linkedProjectId, characterId);
        setCharacters(prev => [...prev, newChar]);
        isNew = true;
      }

      setStatusMessage("Uploading slot assets...");

      // 2. Convert cropped base64 data URLs to blobs and upload them
      const uploadedPaths: Record<string, string> = {};

      for (const slot of data.slots) {
        const imageSrc = data.images[slot.id];
        if (!imageSrc) continue;

        if (imageSrc.startsWith('data:')) {
          setStatusMessage(`Uploading image for ${slot.label}...`);
          const blob = await dataURLtoBlob(imageSrc);
          
          const fileExt = blob.type.split('/')[1] || 'png';
          const assetPath = `characters/${characterId}_${slot.id}.${fileExt}`;
          
          await uploadAsset(data.linkedProjectId, assetPath, blob);
          uploadedPaths[slot.id] = assetPath;
        } else {
          const matchPattern = `/assets/${data.linkedProjectId}/`;
          const idx = imageSrc.indexOf(matchPattern);
          if (idx !== -1) {
            uploadedPaths[slot.id] = imageSrc.substring(idx + matchPattern.length);
          } else {
            uploadedPaths[slot.id] = imageSrc;
          }
        }
      }

      setStatusMessage("Saving character metadata...");

      // 3. Prepare the updates payload
      const characterUpdates: any = {
        name: data.name || "Unnamed Character",
        description: data.role || "",
        personality: data.bio || "",
        avatar_relative_path: uploadedPaths['face'] || null,
        portrait_relative_path: uploadedPaths['profile'] || null,
        fullbody_shot_relative_path: uploadedPaths['full-body'] || null,
      };

      // 4. Serialize custom slots configuration & stats payload
      const configPayload = {
        hp: data.hp,
        energy: data.energy,
        combat: data.combat,
        intellect: data.intellect,
        agility: data.agility,
        templateId: data.templateId,
        orientation: data.orientation,
        bio: data.bio,
        role: data.role,
        slots: data.slots,
        images: uploadedPaths,
      };

      const existingChar = characters.find(c => c.id === characterId);
      characterUpdates.creator_notes = serializeCreatorNotes(configPayload, existingChar?.creator_notes);

      // 5. Patch character creator notes on backend
      const updatedChar = await updateCharacter(data.linkedProjectId, characterId, characterUpdates);
      
      if (isNew) {
        setCharacters(prev => prev.map(c => c.id === 'CREATE_NEW' ? c : (c.id === characterId ? updatedChar : c)));
      } else {
        setCharacters(prev => prev.map(c => c.id === characterId ? updatedChar : c));
      }

      // Update local images with resolved asset URLs
      const resolvedImages = { ...data.images };
      Object.entries(uploadedPaths).forEach(([slotId, assetPath]) => {
        resolvedImages[slotId] = resolveAssetUrl(data.linkedProjectId!, assetPath);
      });

      updateData({
        images: resolvedImages
      });

      setStatusMessage("Sync completed successfully!");
      setStatusType("success");
    } catch (err: any) {
      console.error("Export failed:", err);
      setStatusMessage(`Sync failed: ${err.message || err}`);
      setStatusType("error");
    } finally {
      setExporting(false);
    }
  };

  const handleAddSlot = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSlotLabel.trim()) return;
    
    let aspect: number | undefined = undefined;
    if (newSlotAspect === '1') aspect = 1;
    else if (newSlotAspect === '0.75') aspect = 0.75;
    
    addSlot(newSlotLabel.trim(), aspect);
    setNewSlotLabel('');
  };

  return (
    <div className="sheet-panel-left" style={{ 
      width: '25%', 
      borderRight: '1px solid var(--border-color)', 
      padding: '1.5rem', 
      display: 'flex', 
      flexDirection: 'column', 
      gap: '1.25rem', 
      overflowY: 'auto',
      backgroundColor: 'var(--bg-secondary)',
      color: 'var(--text-main)',
      fontFamily: 'Outfit, sans-serif'
    }}>
      <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, letterSpacing: '-0.02em', background: 'linear-gradient(to right, #fff, #aaa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
        Character Metadata
      </h2>

      {/* SillyTavern Link Panel */}
      <div style={{
        padding: '1rem',
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
      }}>
        <h3 style={{ fontSize: '0.85rem', fontWeight: 700, margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <SyncIcon /> SillyTavern Cards Link
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
          <label style={{ fontSize: '0.7rem', fontWeight: 650, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Linked Project</label>
          <select 
            disabled={exporting || loadingProjects}
            value={data.linkedProjectId || ''} 
            onChange={e => {
              const val = e.target.value || null;
              linkCharacter(val, null);
              setStatusMessage(null);
            }}
            style={{ 
              padding: '0.5rem 0.6rem', 
              background: 'var(--bg-main)', 
              border: '1px solid var(--border-color)', 
              borderRadius: '6px', 
              color: 'var(--text-main)',
              outline: 'none',
              fontSize: '0.8rem',
              cursor: 'pointer'
            }}
          >
            <option value="">-- Select Project --</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
          <label style={{ fontSize: '0.7rem', fontWeight: 650, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Character Card</label>
          <select 
            disabled={!data.linkedProjectId || loadingCharacters || exporting}
            value={data.linkedCharacterId || ''} 
            onChange={e => {
              const val = e.target.value || null;
              linkCharacter(data.linkedProjectId, val);
              setStatusMessage(null);
            }}
            style={{ 
              padding: '0.5rem 0.6rem', 
              background: 'var(--bg-main)', 
              border: '1px solid var(--border-color)', 
              borderRadius: '6px', 
              color: 'var(--text-main)',
              outline: 'none',
              fontSize: '0.8rem',
              cursor: 'pointer',
              opacity: (!data.linkedProjectId || exporting) ? 0.5 : 1
            }}
          >
            <option value="">-- Select Card --</option>
            {data.linkedProjectId && (
              <option value="CREATE_NEW">+ Create New Card</option>
            )}
            {characters.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '0.25rem' }}>
          <button
            onClick={handleImport}
            disabled={!data.linkedProjectId || !data.linkedCharacterId || data.linkedCharacterId === 'CREATE_NEW' || exporting}
            style={{
              padding: '0.5rem 0.6rem',
              fontSize: '0.75rem',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-primary)',
              borderRadius: '6px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              justifyContent: 'center',
              transition: 'all 0.2s'
            }}
            className="ghost-button"
          >
            <DownloadIcon /> Import Card
          </button>
          
          <button
            onClick={handleExport}
            disabled={!data.linkedProjectId || exporting}
            style={{
              padding: '0.5rem 0.6rem',
              fontSize: '0.75rem',
              background: 'linear-gradient(135deg, var(--accent) 0%, #5a4bcf 100%)',
              color: 'white',
              borderRadius: '6px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              justifyContent: 'center',
              transition: 'all 0.2s',
              boxShadow: '0 2px 8px var(--accent-glow)'
            }}
            className="primary"
          >
            <SyncIcon /> Sync / Export
          </button>
        </div>

        {statusMessage && (
          <div style={{
            padding: '0.5rem 0.75rem',
            borderRadius: '6px',
            fontSize: '0.75rem',
            border: '1px solid',
            borderColor: statusType === 'success' ? 'rgba(74, 222, 128, 0.3)' : statusType === 'error' ? 'rgba(255, 87, 87, 0.3)' : 'rgba(124, 106, 255, 0.3)',
            backgroundColor: statusType === 'success' ? 'rgba(74, 222, 128, 0.05)' : statusType === 'error' ? 'rgba(255, 87, 87, 0.05)' : 'rgba(124, 106, 255, 0.05)',
            color: statusType === 'success' ? 'var(--success)' : statusType === 'error' ? 'var(--danger)' : 'var(--text-secondary)',
            wordBreak: 'break-word'
          }}>
            {statusMessage}
          </div>
        )}
      </div>
      
      {/* Standard Fields */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        <label style={{ fontSize: '0.78rem', fontWeight: 650, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Character Name</label>
        <input 
          type="text" 
          placeholder="e.g. Lina Moreau" 
          value={data.name} 
          onChange={e => updateData({ name: e.target.value })} 
          style={{ 
            padding: '0.65rem 0.75rem', 
            background: 'var(--bg-main)', 
            border: '1px solid var(--border-color)', 
            borderRadius: '8px', 
            color: 'var(--text-main)',
            outline: 'none',
            fontSize: '0.88rem'
          }}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        <label style={{ fontSize: '0.78rem', fontWeight: 650, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Role / Archetype</label>
        <input 
          type="text" 
          placeholder="e.g. Rebel Inventor, Cyber Samurai" 
          value={data.role} 
          onChange={e => updateData({ role: e.target.value })} 
          style={{ 
            padding: '0.65rem 0.75rem', 
            background: 'var(--bg-main)', 
            border: '1px solid var(--border-color)', 
            borderRadius: '8px', 
            color: 'var(--text-main)',
            outline: 'none',
            fontSize: '0.88rem'
          }}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        <label style={{ fontSize: '0.78rem', fontWeight: 650, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Select Template</label>
        <select 
          value={data.templateId} 
          onChange={e => updateData({ templateId: e.target.value })}
          style={{ 
            padding: '0.65rem 0.75rem', 
            background: 'var(--bg-main)', 
            border: '1px solid var(--border-color)', 
            borderRadius: '8px', 
            color: 'var(--text-main)',
            outline: 'none',
            fontSize: '0.88rem',
            cursor: 'pointer'
          }}
        >
          <option value="lina-moreau">Cyberpunk (Lina Moreau)</option>
          <option value="classic-fantasy">Classic Fantasy (Parchment)</option>
          <option value="modern-minimal">Modern Minimalist</option>
          <option value="production-sheet">Production Sheet (Complex)</option>
          {customTemplates.map((t: any) => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </select>
      </div>

      {data.templateId === 'production-sheet' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.5rem' }}>
          <label style={{ fontSize: '0.78rem', fontWeight: 650, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Theme Color</label>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            {['#cba171', '#c0c0c0', '#b22222', '#50c878', '#0f52ba', '#9966cc'].map(color => (
              <button
                key={color}
                onClick={(e) => { e.preventDefault(); updateData({ themeColor: color }); }}
                style={{
                  width: '24px', height: '24px', borderRadius: '50%', backgroundColor: color,
                  border: data.themeColor === color ? '2px solid white' : '2px solid transparent',
                  cursor: 'pointer', outline: 'none', padding: 0
                }}
                title={color}
              />
            ))}
            <input 
              type="color" 
              value={data.themeColor || '#cba171'}
              onChange={e => updateData({ themeColor: e.target.value })}
              style={{
                width: '30px', height: '30px', border: 'none', background: 'none', cursor: 'pointer', padding: 0, marginLeft: '0.5rem'
              }}
              title="Custom Color"
            />
          </div>
        </div>
      )}

      {data.templateId !== 'production-sheet' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          <label style={{ fontSize: '0.78rem', fontWeight: 650, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Biography</label>
          <textarea 
            placeholder="Describe your character's origin and skills..." 
            value={data.bio} 
            onChange={e => updateData({ bio: e.target.value })} 
            rows={3}
            style={{ 
              padding: '0.65rem 0.75rem', 
              background: 'var(--bg-main)', 
              border: '1px solid var(--border-color)', 
              borderRadius: '8px', 
              color: 'var(--text-main)',
              outline: 'none',
              fontSize: '0.88rem',
              resize: 'vertical',
              fontFamily: 'inherit'
            }}
          />
        </div>
      )}

      {data.templateId === 'production-sheet' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', borderTop: '1px solid var(--border-color)', paddingTop: '1.25rem' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 700, margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)' }}>
            Production Slots
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: 0 }}>
            Use the SDXL Generator to assign images to the required production slots.
          </p>
          <div style={{ fontSize: '0.75rem', color: 'var(--accent)', background: 'rgba(124, 106, 255, 0.1)', padding: '0.5rem', borderRadius: '4px' }}>
            Filled Slots: {Object.keys(data.images).filter(k => 
              k.startsWith('turnaround-') || k.startsWith('expr-') || k.startsWith('profile-') || k.startsWith('equip-') || k.startsWith('mat-') || k.startsWith('detail-') || k.startsWith('pose-')
            ).length} / 59
          </div>
        </div>
      )}

      {data.templateId !== 'production-sheet' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', borderTop: '1px solid var(--border-color)', paddingTop: '1.25rem' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 700, margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)' }}>
            Character Stats
          </h3>

          {[
            { label: 'HP / Health', key: 'hp' },
            { label: 'Energy / Mana', key: 'energy' },
            { label: 'Combat / Attack', key: 'combat' },
            { label: 'Intellect / Skill', key: 'intellect' },
            { label: 'Agility / Speed', key: 'agility' }
          ].map(({ label, key }) => (
            <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 600 }}>
                <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                <span style={{ color: 'var(--accent)' }}>{(data as any)[key]}%</span>
              </div>
              <input 
                type="range" 
                min="0" 
                max="100" 
                value={(data as any)[key]} 
                onChange={e => updateData({ [key]: parseInt(e.target.value) })}
                style={{ 
                  width: '100%', 
                  accentColor: 'var(--accent)',
                  height: '4px',
                  borderRadius: '2px',
                  background: 'var(--border-color)',
                  cursor: 'pointer'
                }}
              />
            </div>
          ))}
        </div>
      )}

      {data.templateId === 'production-sheet' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', borderTop: '1px solid var(--border-color)', paddingTop: '1.25rem' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 700, margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)' }}>
            Production Details
          </h3>
          {[
            { label: 'Subtitle/Nickname', key: 'subtitle' },
            { label: 'Age', key: 'age' },
            { label: 'Height', key: 'height' },
            { label: 'Weight', key: 'weight' },
            { label: 'Origin', key: 'origin' },
            { label: 'Affiliation', key: 'affiliation' },
            { label: 'Status', key: 'status' }
          ].map(({ label, key }) => (
            <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              <label style={{ fontSize: '0.78rem', fontWeight: 650, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
              <input 
                type="text" 
                value={(data.productionData as any)?.[key] || ''} 
                onChange={e => updateData({ productionData: { [key]: e.target.value } })} 
                style={{ 
                  padding: '0.5rem 0.6rem', 
                  background: 'var(--bg-main)', 
                  border: '1px solid var(--border-color)', 
                  borderRadius: '6px', 
                  color: 'var(--text-main)',
                  outline: 'none',
                  fontSize: '0.8rem'
                }}
              />
            </div>
          ))}
          {[
            { label: 'Overview', key: 'overview' },
            { label: 'Personality & Motivations', key: 'personality' },
            { label: 'Competences & Aptitudes', key: 'competences' },
            { label: 'History & Context', key: 'history' },
            { label: 'Notes & References', key: 'notes' }
          ].map(({ label, key }) => (
            <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              <label style={{ fontSize: '0.78rem', fontWeight: 650, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
              <textarea 
                value={(data.productionData as any)?.[key] || ''} 
                onChange={e => updateData({ productionData: { [key]: e.target.value } })} 
                rows={2}
                style={{ 
                  padding: '0.5rem 0.6rem', 
                  background: 'var(--bg-main)', 
                  border: '1px solid var(--border-color)', 
                  borderRadius: '6px', 
                  color: 'var(--text-main)',
                  outline: 'none',
                  fontSize: '0.8rem',
                  resize: 'vertical',
                  fontFamily: 'inherit'
                }}
              />
            </div>
          ))}
        </div>
      )}

      {data.templateId !== 'production-sheet' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', borderTop: '1px solid var(--border-color)', paddingTop: '1.25rem' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 700, margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)' }}>
            Asset Slots Manager
          </h3>

        <form onSubmit={handleAddSlot} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', background: 'rgba(255, 255, 255, 0.01)', border: '1px solid var(--border-color)', padding: '0.75rem', borderRadius: '6px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <label style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Slot Name</label>
            <input 
              type="text" 
              placeholder="e.g. Companion, Weapon" 
              value={newSlotLabel} 
              onChange={e => setNewSlotLabel(e.target.value)}
              style={{ 
                padding: '0.45rem 0.55rem', 
                background: 'var(--bg-main)', 
                border: '1px solid var(--border-color)', 
                borderRadius: '4px', 
                color: 'var(--text-main)',
                fontSize: '0.8rem'
              }}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <label style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Crop Aspect Ratio</label>
            <select 
              value={newSlotAspect} 
              onChange={e => setNewSlotAspect(e.target.value)}
              style={{ 
                padding: '0.45rem 0.55rem', 
                background: 'var(--bg-main)', 
                border: '1px solid var(--border-color)', 
                borderRadius: '4px', 
                color: 'var(--text-main)',
                fontSize: '0.8rem',
                cursor: 'pointer'
              }}
            >
              <option value="1">Square (1:1)</option>
              <option value="0.75">Portrait (3:4)</option>
              <option value="free">Free Aspect</option>
            </select>
          </div>
          <button 
            type="submit"
            style={{ 
              marginTop: '0.25rem',
              padding: '0.45rem', 
              background: 'var(--bg-hover)', 
              border: '1px solid var(--border-color)', 
              borderRadius: '4px', 
              color: 'var(--text-primary)',
              fontSize: '0.75rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.25rem'
            }}
          >
            <PlusIcon /> Add Asset Slot
          </button>
        </form>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', maxHeight: '180px', overflowY: 'auto', paddingRight: '2px' }}>
          {data.slots.map(slot => {
            const isCustom = slot.id.startsWith('custom-');
            const aspectLabel = slot.aspect === 1 ? 'Square 1:1' : slot.aspect === 0.75 ? 'Portrait 3:4' : 'Free';
            return (
              <div 
                key={slot.id} 
                style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'space-between', 
                  padding: '0.45rem 0.6rem', 
                  background: isCustom ? 'rgba(124, 106, 255, 0.03)' : 'rgba(255, 255, 255, 0.01)', 
                  border: '1px solid var(--border-color)', 
                  borderRadius: '6px',
                  transition: 'all 0.2s'
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.05rem' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>{slot.label}</span>
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Aspect: {aspectLabel}</span>
                </div>

                {isCustom ? (
                  <button 
                    onClick={() => removeSlot(slot.id)}
                    style={{ 
                      padding: '0.35rem', 
                      background: 'transparent', 
                      color: 'var(--text-muted)',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={e => {
                      (e.currentTarget.style.color = 'var(--danger)');
                      (e.currentTarget.style.background = 'rgba(255, 87, 87, 0.08)');
                    }}
                    onMouseLeave={e => {
                      (e.currentTarget.style.color = 'var(--text-muted)');
                      (e.currentTarget.style.background = 'transparent');
                    }}
                    title="Remove custom slot"
                  >
                    <TrashIcon />
                  </button>
                ) : (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', fontSize: '0.65rem', color: 'var(--text-muted)', background: 'rgba(255,255,255,0.04)', padding: '0.15rem 0.35rem', borderRadius: '4px' }}>
                    <LockIcon /> System
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
      )}

      {/* Reset to Default Button */}
      <div style={{ marginTop: '0.5rem', borderTop: '1px solid var(--border-color)', paddingTop: '1.25rem' }}>
        <button
          onClick={() => {
            if (window.confirm("Are you sure you want to reset all data and slots to default? This will clear all uploaded images in memory.")) {
              resetToDefault();
              setStatusMessage("Reset to defaults successfully.");
              setStatusType("success");
            }
          }}
          style={{
            width: '100%',
            padding: '0.6rem',
            fontSize: '0.8rem',
            background: 'rgba(255, 87, 87, 0.03)',
            border: '1px solid rgba(255, 87, 87, 0.2)',
            color: 'var(--danger)',
            borderRadius: '8px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.35rem',
            fontWeight: 600,
            transition: 'all 0.2s'
          }}
          onMouseEnter={e => {
            (e.currentTarget.style.background = 'rgba(255, 87, 87, 0.08)');
            (e.currentTarget.style.borderColor = 'var(--danger)');
          }}
          onMouseLeave={e => {
            (e.currentTarget.style.background = 'rgba(255, 87, 87, 0.03)');
            (e.currentTarget.style.borderColor = 'rgba(255, 87, 87, 0.2)');
          }}
        >
          <ResetIcon /> Reset to Defaults
        </button>
      </div>
    </div>
  );
}
