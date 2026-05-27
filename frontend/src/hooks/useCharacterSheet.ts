import { useState, useEffect, useCallback } from 'react';

export interface AssetSlot {
  id: string;
  label: string;
  aspect?: number; // 1 for square, 0.75 for 3:4, undefined for free
}

export interface ProductionData {
  subtitle?: string;
  age?: string;
  height?: string;
  weight?: string;
  origin?: string;
  affiliation?: string;
  status?: string;
  overview?: string;
  personality?: string;
  competences?: string;
  history?: string;
  notes?: string;
}

export interface CharacterData {
  name: string;
  role: string;
  templateId: string;
  orientation: 'portrait' | 'landscape';
  images: Record<string, string>; // slotId -> base64 or URL/path
  hp: number;
  energy: number;
  combat: number;
  intellect: number;
  agility: number;
  bio: string;
  slots: AssetSlot[];
  linkedProjectId: string | null;
  linkedCharacterId: string | null;
  productionData?: ProductionData;
  themeColor?: string;
  activeCollectionId: string | null;
}

const DEFAULT_SLOTS: AssetSlot[] = [
  { id: 'face', label: 'Face Portrait', aspect: 1 },
  { id: 'profile', label: 'Profile View', aspect: 1 },
  { id: 'full-body', label: 'Full Body', aspect: 0.75 }
];

const DEFAULT_STATE: CharacterData = {
  name: '',
  role: '',
  templateId: 'lina-moreau',
  themeColor: '#cba171',
  orientation: 'landscape',
  images: {},
  hp: 80,
  energy: 90,
  combat: 75,
  intellect: 85,
  agility: 70,
  bio: '',
  slots: DEFAULT_SLOTS,
  linkedProjectId: null,
  linkedCharacterId: null,
  productionData: {},
  activeCollectionId: null
};

const STORAGE_KEY = 'mklan_character_sheet_v2';

export function parseCreatorNotes(notes: string): any {
  if (!notes) return null;
  // Match both \n and \r\n line endings
  const match = notes.match(/---CHARACTER_SHEET_DATA---\r?\n([\s\S]+)/);
  if (match && match[1]) {
    try {
      return JSON.parse(match[1]);
    } catch (_) {
      return null;
    }
  }
  return null;
}

export function serializeCreatorNotes(config: any, existingNotes?: string): string {
  const marker = '---CHARACTER_SHEET_DATA---';
  const newBlock = `${marker}\n${JSON.stringify(config, null, 2)}`;
  if (!existingNotes) return newBlock;
  const index = existingNotes.indexOf(marker);
  if (index !== -1) {
    return existingNotes.substring(0, index) + newBlock;
  }
  return existingNotes + (existingNotes.endsWith('\n') ? '' : '\n') + newBlock;
}

export function useCharacterSheet() {
  const [data, setData] = useState<CharacterData>(() => {
    // Recover from localStorage if available, or fall back to default
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && Array.isArray(parsed.slots)) {
          return { ...DEFAULT_STATE, ...parsed };
        }
      }
    } catch (_) {}
    
    return DEFAULT_STATE;
  });

  // Handle localStorage persistence via useEffect to avoid blocking renders
  // and violating state updater callback purity rules.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (err) {
      console.error('Failed to save character sheet data to localStorage:', err);
    }
  }, [data]);

  const updateData = useCallback((updates: Partial<CharacterData>) => {
    setData(prev => {
      if (updates.productionData) {
        return {
          ...prev,
          ...updates,
          productionData: { ...(prev.productionData || {}), ...updates.productionData }
        };
      }
      return { ...prev, ...updates };
    });
  }, []);

  const assignImage = useCallback((slot: string, imageSrc: string) => {
    setData(prev => ({
      ...prev,
      images: { ...prev.images, [slot]: imageSrc }
    }));
  }, []);

  const addSlot = useCallback((label: string, aspect?: number) => {
    const id = `custom-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    setData(prev => ({
      ...prev,
      slots: [...prev.slots, { id, label, aspect }]
    }));
  }, []);

  const removeSlot = useCallback((slotId: string) => {
    setData(prev => {
      const newImages = { ...prev.images };
      delete newImages[slotId];
      return {
        ...prev,
        slots: prev.slots.filter(s => s.id !== slotId),
        images: newImages
      };
    });
  }, []);

  const linkCharacter = useCallback((projectId: string | null, characterId: string | null) => {
    setData(prev => ({
      ...prev,
      linkedProjectId: projectId,
      linkedCharacterId: characterId
    }));
  }, []);

  const resetToDefault = useCallback(() => {
    setData(DEFAULT_STATE);
  }, []);

  return { data, updateData, assignImage, addSlot, removeSlot, resetToDefault, linkCharacter };
}
