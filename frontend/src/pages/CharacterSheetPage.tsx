import React from 'react';
import { useCharacterSheet } from '../hooks/useCharacterSheet';
import { CharacterForm } from '../components/CharacterForm';
import { TemplatePreview } from '../components/TemplatePreview';
import { ImageGeneratorCropper } from '../components/ImageGeneratorCropper';
import { CharacterAssetGallery } from '../components/CharacterAssetGallery';
import { TemplateEditor } from '../components/TemplateEditor';

export const PRODUCTION_SLOTS = [
  { id: 'turnaround-front', label: 'Turnaround: Front', aspect: 0.5 },
  { id: 'turnaround-34front', label: 'Turnaround: 3/4 Front', aspect: 0.5 },
  { id: 'turnaround-side', label: 'Turnaround: Side', aspect: 0.5 },
  { id: 'turnaround-back', label: 'Turnaround: Back', aspect: 0.5 },
  { id: 'turnaround-34back', label: 'Turnaround: 3/4 Back', aspect: 0.5 },
  { id: 'expr-neutral', label: 'Expr: Neutral', aspect: 1 },
  { id: 'expr-focus', label: 'Expr: Focus', aspect: 1 },
  { id: 'expr-determined', label: 'Expr: Determined', aspect: 1 },
  { id: 'expr-alert', label: 'Expr: Alert', aspect: 1 },
  { id: 'expr-sad', label: 'Expr: Sad', aspect: 1 },
  { id: 'expr-concentrated', label: 'Expr: Concentrated', aspect: 1 },
  { id: 'expr-anxious', label: 'Expr: Anxious', aspect: 1 },
  { id: 'expr-suspicious', label: 'Expr: Suspicious', aspect: 1 },
  { id: 'profile-left', label: 'Profile: Left', aspect: 1 },
  { id: 'profile-34left', label: 'Profile: 3/4 Left', aspect: 1 },
  { id: 'profile-34right', label: 'Profile: 3/4 Right', aspect: 1 },
  { id: 'profile-right', label: 'Profile: Right', aspect: 1 },
  { id: 'equip-head', label: 'Equip: Head', aspect: 1 },
  { id: 'equip-neck', label: 'Equip: Neck', aspect: 1 },
  { id: 'equip-torso', label: 'Equip: Torso', aspect: 1 },
  { id: 'equip-arms', label: 'Equip: Arms', aspect: 1 },
  { id: 'equip-forearms', label: 'Equip: Forearms', aspect: 1 },
  { id: 'equip-hands', label: 'Equip: Hands', aspect: 1 },
  { id: 'equip-waist', label: 'Equip: Waist', aspect: 1 },
  { id: 'equip-hips', label: 'Equip: Hips', aspect: 1 },
  { id: 'equip-legs', label: 'Equip: Legs', aspect: 1 },
  { id: 'equip-knees', label: 'Equip: Knees', aspect: 1 },
  { id: 'equip-feet', label: 'Equip: Feet', aspect: 1 },
  { id: 'grid-equip-1', label: 'Grid: Equip 1', aspect: 1 },
  { id: 'grid-equip-2', label: 'Grid: Equip 2', aspect: 1 },
  { id: 'grid-equip-3', label: 'Grid: Equip 3', aspect: 1 },
  { id: 'grid-equip-4', label: 'Grid: Equip 4', aspect: 1 },
  { id: 'grid-equip-5', label: 'Grid: Equip 5', aspect: 1 },
  { id: 'grid-equip-6', label: 'Grid: Equip 6', aspect: 1 },
  { id: 'grid-equip-7', label: 'Grid: Equip 7', aspect: 1 },
  { id: 'grid-equip-8', label: 'Grid: Equip 8', aspect: 1 },
  { id: 'mat-1', label: 'Material 1', aspect: 1 },
  { id: 'mat-2', label: 'Material 2', aspect: 1 },
  { id: 'mat-3', label: 'Material 3', aspect: 1 },
  { id: 'mat-4', label: 'Material 4', aspect: 1 },
  { id: 'mat-5', label: 'Material 5', aspect: 1 },
  { id: 'mat-6', label: 'Material 6', aspect: 1 },
  { id: 'mat-7', label: 'Material 7', aspect: 1 },
  { id: 'mat-8', label: 'Material 8', aspect: 1 },
  { id: 'detail-1', label: 'Detail 1', aspect: 1 },
  { id: 'detail-2', label: 'Detail 2', aspect: 1 },
  { id: 'detail-3', label: 'Detail 3', aspect: 1 },
  { id: 'detail-4', label: 'Detail 4', aspect: 1 },
  { id: 'detail-5', label: 'Detail 5', aspect: 1 },
  { id: 'detail-6', label: 'Detail 6', aspect: 1 },
  { id: 'detail-7', label: 'Detail 7', aspect: 1 },
  { id: 'pose-1', label: 'Pose 1', aspect: 0.75 },
  { id: 'pose-2', label: 'Pose 2', aspect: 0.75 },
  { id: 'pose-3', label: 'Pose 3', aspect: 0.75 },
  { id: 'pose-4', label: 'Pose 4', aspect: 0.75 },
  { id: 'pose-5', label: 'Pose 5', aspect: 0.75 },
  { id: 'pose-6', label: 'Pose 6', aspect: 0.75 },
  { id: 'pose-7', label: 'Pose 7', aspect: 0.75 },
  { id: 'pose-8', label: 'Pose 8', aspect: 0.75 }
];

export default function CharacterSheetPage() {
  const { data, updateData, assignImage, addSlot, removeSlot, linkCharacter, resetToDefault } = useCharacterSheet();

  const activeSlots = data.templateId === 'production-sheet' ? PRODUCTION_SLOTS : data.slots;

  // Track selected slot globally so clicking in TemplatePreview updates the Cropper's active slot
  const [activeSlotId, setActiveSlotId] = React.useState<string>(activeSlots[0]?.id || 'face');
  const [reopenImageB64, setReopenImageB64] = React.useState<string | null>(null);
  const [centerTab, setCenterTab] = React.useState<'generator' | 'editor'>('generator');

  const handleImageGenerated = async (assetId: string) => {
    if (!data.activeCollectionId || !assetId) return;
    try {
      await fetch(`/api/media/collections/${data.activeCollectionId}/assets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_ids: [assetId] })
      });
      // Force a re-render of the gallery
      updateData({}); 
    } catch (e) {
      console.error("Failed to add generated image to collection", e);
    }
  };

  const handleReopenAsset = async (imgUrl: string) => {
    try {
      const res = await fetch(imgUrl);
      const blob = await res.blob();
      const reader = new FileReader();
      reader.onloadend = () => setReopenImageB64(reader.result as string);
      reader.readAsDataURL(blob);
    } catch (e) {
      console.error("Failed to fetch image for reopening", e);
    }
  };

  return (
    <div className="sheet-container">
      {/* Left Panel: Form */}
      <CharacterForm 
        data={data} 
        updateData={updateData} 
        addSlot={addSlot} 
        removeSlot={removeSlot} 
        linkCharacter={linkCharacter} 
        resetToDefault={resetToDefault} 
      />

      {/* Center Panel: Tabs, Gallery, Generator/Editor */}
      <div className="sheet-panel-center" style={{ 
        padding: '1.5rem', 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '1.25rem', 
        backgroundColor: 'var(--bg-main)',
        color: 'var(--text-main)',
        fontFamily: 'Outfit, sans-serif'
      }}>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-color)' }}>
          <button 
            onClick={() => setCenterTab('generator')}
            style={{ flex: 1, padding: '0.75rem', background: centerTab === 'generator' ? 'rgba(255,255,255,0.05)' : 'transparent', color: centerTab === 'generator' ? 'var(--accent)' : 'var(--text-secondary)', border: 'none', borderBottom: centerTab === 'generator' ? '2px solid var(--accent)' : '2px solid transparent', cursor: 'pointer', fontWeight: 600 }}
          >
            SDXL Generator & Assets
          </button>
          <button 
            onClick={() => setCenterTab('editor')}
            style={{ flex: 1, padding: '0.75rem', background: centerTab === 'editor' ? 'rgba(255,255,255,0.05)' : 'transparent', color: centerTab === 'editor' ? 'var(--accent)' : 'var(--text-secondary)', border: 'none', borderBottom: centerTab === 'editor' ? '2px solid var(--accent)' : '2px solid transparent', cursor: 'pointer', fontWeight: 600 }}
          >
            Template Editor
          </button>
        </div>

        {centerTab === 'generator' ? (
          <>
            <CharacterAssetGallery 
              characterName={data.name} 
              activeCollectionId={data.activeCollectionId} 
              onCollectionSelect={(id) => updateData({ activeCollectionId: id })}
              onReopenAsset={handleReopenAsset}
            />
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, letterSpacing: '-0.02em', background: 'linear-gradient(to right, #fff, #aaa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              SDXL Generator
            </h2>
            <ImageGeneratorCropper 
              slots={activeSlots} 
              onAssignSlot={assignImage} 
              activeSlotId={activeSlotId}
              onSlotSelect={setActiveSlotId}
              onImageGenerated={handleImageGenerated}
              reopenImageB64={reopenImageB64}
              onReopenComplete={() => setReopenImageB64(null)}
            />
          </>
        ) : (
          <TemplateEditor characterData={data} updateCharacterData={updateData} />
        )}
      </div>

      {/* Right Panel: Template Preview */}
      <TemplatePreview data={data} updateData={updateData} onSlotSelect={setActiveSlotId} />
    </div>
  );
}
