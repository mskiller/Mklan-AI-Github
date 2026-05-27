import React from 'react';
import html2canvas from 'html2canvas';
import { CharacterData, AssetSlot } from '../hooks/useCharacterSheet';

// Simple hex to rgba helper
const hexToRgba = (hex: string, alpha: number) => {
  const r = parseInt(hex.slice(1, 3), 16) || 203;
  const g = parseInt(hex.slice(3, 5), 16) || 161;
  const b = parseInt(hex.slice(5, 7), 16) || 113;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

interface Props {
  data: CharacterData;
  updateData: (updates: Partial<CharacterData>) => void;
  onSlotSelect?: (slotId: string) => void;
}

const toBase64 = async (url: string): Promise<string> => {
  if (url.startsWith('data:')) {
    return url;
  }
  try {
    const response = await fetch(url);
    const blob = await response.blob();
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch (err) {
    console.error("Failed to convert image to base64:", url, err);
    return url;
  }
};

function styleToString(style?: React.CSSProperties): string {
  if (!style) return '';
  return Object.entries(style)
    .map(([key, val]) => {
      if (val === undefined || val === null) return '';
      const cssKey = key.replace(/([A-Z])/g, '-$1').toLowerCase();
      return `${cssKey}: ${val};`;
    })
    .filter(Boolean)
    .join(' ');
}

export function TemplatePreview({ data, updateData, onSlotSelect }: Props) {
  const [previewHeight, setPreviewHeight] = React.useState(data.orientation === 'landscape' ? 800 : 1200);
  const [isExportingHTML, setIsExportingHTML] = React.useState(false);
  const [customTemplate, setCustomTemplate] = React.useState<any | null>(null);

  React.useEffect(() => {
    if (data.templateId && data.templateId.startsWith('custom-template-')) {
      const raw = localStorage.getItem('mklan_custom_templates');
      if (raw) {
        try {
          const templates = JSON.parse(raw);
          const found = templates.find((t: any) => t.id === data.templateId);
          if (found) {
            setCustomTemplate(found);
            return;
          }
        } catch (_) {}
      }
    }
    setCustomTemplate(null);
  }, [data.templateId, data.slots]);

  React.useEffect(() => {
    const el = document.getElementById('character-template-preview');
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setPreviewHeight(entry.contentRect.height);
      }
    });
    observer.observe(el);

    return () => {
      observer.disconnect();
    };
  }, [data.slots, data.orientation, data.images]); // re-run if slots, orientation or images change

  const handleExport = async () => {
    const element = document.getElementById('character-template-preview');
    if (!element) return;
    try {
      // Temporarily remove transform scale for full-res capture
      const originalTransform = element.style.transform;
      element.style.transform = 'none';
      
      const canvas = await html2canvas(element, { 
        scale: 2, // High resolution output
        useCORS: true,
        logging: false
      });
      
      element.style.transform = originalTransform;
      
      const dataUrl = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.download = `${data.name.replace(/\s+/g, '_') || 'character'}_sheet.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error("Export failed:", err);
      alert("Failed to export character sheet.");
    }
  };

  const handleExportHTML = async () => {
    setIsExportingHTML(true);
    try {
      // 1. Gather all images and convert to base64
      const base64Images: Record<string, string> = {};
      for (const slot of data.slots) {
        const imgUrl = data.images[slot.id];
        if (imgUrl) {
          base64Images[slot.id] = await toBase64(imgUrl);
        }
      }
      if (customTemplate && customTemplate.backgroundImage) {
        try {
          base64Images['backgroundImage'] = await toBase64(customTemplate.backgroundImage);
        } catch (_) {}
      }

      // 2. Determine template style properties for HTML export
      const isProduction = data.templateId === 'production-sheet';
      const containerStyle: React.CSSProperties = {
        width: isProduction ? '2000px' : (data.orientation === 'landscape' ? '1200px' : '800px'),
        minHeight: isProduction ? '1200px' : (data.orientation === 'landscape' ? '800px' : '1200px'),
        height: 'auto',
        display: 'flex',
        flexDirection: 'column',
        padding: '2.5rem',
        boxSizing: 'border-box',
        fontFamily: fontClass,
        ...templateStyle
      };

      const renderCustomHTML = () => {
        if (!customTemplate) return '';
        const bgImg = base64Images['backgroundImage'] || customTemplate.backgroundImage;
        return `
          <div style="position: relative; width: 100%; aspect-ratio: 1.77; min-height: 600px; background-image: url(${bgImg}); background-size: cover; background-position: center; border: 3px solid ${statBarColor}; border-radius: 8px; overflow: hidden; box-sizing: border-box;">
            ${customTemplate.slots.map((slot: any) => {
              const imgB64 = base64Images[slot.id];
              const isBio = slot.id === 'bio' || slot.label.toLowerCase() === 'biography' || slot.label.toLowerCase() === 'bio';
              const isStats = slot.id === 'stats' || slot.label.toLowerCase() === 'stats' || slot.label.toLowerCase() === 'statistics';
              
              if (isBio) {
                return `
                  <div style="position: absolute; left: ${slot.x}%; top: ${slot.y}%; width: ${slot.w}%; height: ${slot.h}%; box-sizing: border-box; z-index: 10; padding: 0.5rem; overflow-y: auto; font-size: 0.85rem; background: rgba(0,0,0,0.6); color: #fff; border: 1px solid rgba(255,255,255,0.1);">
                    <strong>Biography</strong>
                    <p style="margin: 0.2rem 0 0 0; white-space: pre-wrap;">${data.bio || 'No biography provided.'}</p>
                  </div>
                `;
              }
              if (isStats) {
                return `
                  <div style="position: absolute; left: ${slot.x}%; top: ${slot.y}%; width: ${slot.w}%; height: ${slot.h}%; box-sizing: border-box; z-index: 10; padding: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.75rem; justify-content: center; background: rgba(0,0,0,0.6); color: #fff; border: 1px solid rgba(255,255,255,0.1);">
                    ${[
                      { label: 'HP', value: data.hp },
                      { label: 'Energy', value: data.energy },
                      { label: 'Combat', value: data.combat },
                      { label: 'Intellect', value: data.intellect },
                      { label: 'Agility', value: data.agility }
                    ].map(({ label, value }) => `
                      <div style="display: flex; flex-direction: column; gap: 0.1rem;">
                        <div style="display: flex; justify-content: space-between; font-weight: bold;">
                          <span>${label}</span>
                          <span>${value}%</span>
                        </div>
                        <div style="width: 100%; height: 6px; background: ${statTrackColor}; border-radius: 3px; overflow: hidden;">
                          <div style="width: ${value}%; height: 100%; background: ${statBarColor};"></div>
                        </div>
                      </div>
                    `).join('')}
                  </div>
                `;
              }
              return `
                <div style="position: absolute; left: ${slot.x}%; top: ${slot.y}%; width: ${slot.w}%; height: ${slot.h}%; box-sizing: border-box; z-index: 10; ${styleToString(cardSlotStyle)}">
                  ${imgB64 ? `
                    <img src="${imgB64}" style="width: 100%; height: 100%; object-fit: cover;" />
                  ` : `
                    <div style="display: flex; align-items: center; justify-content: center; height: 100%; background: rgba(0,0,0,0.4); color: ${statBarColor}; font-weight: bold; font-size: 0.85rem; padding: 0.2rem; text-align: center;">
                      ${slot.label}
                    </div>
                  `}
                </div>
              `;
            }).join('')}
          </div>
        `;
      };

      const customSlots = data.slots.filter(s => s.id !== 'face' && s.id !== 'profile' && s.id !== 'full-body');
      
      const renderCustomSlotsHTML = () => {
        if (customSlots.length === 0) return '';
        
        return `
          <div style="margin-top: 2.5rem; border-top: ${data.templateId === 'modern-minimal' ? '2px solid #111' : '1px solid rgba(255, 255, 255, 0.1)'}; padding-top: 1.5rem; width: 100%;">
            <h3 style="margin: 0 0 1.5rem 0; font-size: 1.4rem; text-transform: uppercase; letter-spacing: 2px; text-align: center; color: ${data.templateId === 'lina-moreau' ? '#00f0ff' : data.templateId === 'classic-fantasy' ? '#5c3d2e' : '#111'}; ${data.templateId === 'lina-moreau' ? 'text-shadow: 0 0 8px rgba(0, 240, 255, 0.4);' : ''} font-family: ${fontClass};">
              Character Asset Portfolio
            </h3>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; width: 100%;">
              ${customSlots.map(slot => {
                const imgB64 = base64Images[slot.id];
                return `
                  <div style="display: flex; flex-direction: column; gap: 0.6rem; align-items: center;">
                    <div style="width: 100%; aspect-ratio: ${slot.aspect ? String(slot.aspect) : '1'}; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; min-height: 160px; box-sizing: border-box; ${styleToString(cardSlotStyle)}">
                      ${imgB64 ? `
                        <img src="${imgB64}" alt="${slot.label}" style="width: 100%; height: 100%; object-fit: cover;" />
                      ` : `
                        <span style="${styleToString(slotLabelStyle)}; font-size: 0.85rem; text-align: center; padding: 0.5rem;">${slot.label}</span>
                      `}
                    </div>
                    <span style="font-size: 0.85rem; font-weight: 700; text-transform: uppercase; text-align: center; color: ${data.templateId === 'lina-moreau' ? '#ff007f' : data.templateId === 'classic-fantasy' ? '#8c593b' : '#666'};">
                      ${slot.label}
                    </span>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        `;
      };

      const renderLandscapeHTML = () => {
        const fullBodyB64 = base64Images['full-body'];
        const faceB64 = base64Images['face'];
        const profileB64 = base64Images['profile'];
        
        return `
          <div style="display: grid; grid-template-columns: 1.2fr 1fr; gap: 2.5rem; flex: 1; min-height: 0;">
            <!-- Left Side: Body Slot + Biography -->
            <div style="display: flex; flex-direction: column; gap: 1.5rem;">
              <div style="flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; min-height: 340px; ${styleToString(cardSlotStyle)}">
                ${fullBodyB64 ? `
                  <img src="${fullBodyB64}" alt="Full Body" style="width: 100%; height: 100%; object-fit: cover;" />
                ` : `
                  <span style="${styleToString(slotLabelStyle)}">Full Body Slot</span>
                `}
              </div>
              <div style="height: 150px; display: flex; flex-direction: column; gap: 0.5rem;">
                <span style="${styleToString(slotLabelStyle)}; font-size: 0.9rem;">Biography</span>
                <div class="bio-box" style="flex: 1; padding: 0.8rem; overflow-y: auto; border: ${data.templateId === 'modern-minimal' ? '1px solid #111' : '1px solid rgba(255,255,255,0.08)'}; background: rgba(0,0,0,0.1); border-radius: 4px; ${styleToString(textStyle)}">
                  ${data.bio ? data.bio.replace(/\n/g, '<br/>') : 'No biography provided.'}
                </div>
              </div>
            </div>
            
            <!-- Right Side: Portrait Slots + Stats -->
            <div style="display: flex; flex-direction: column; gap: 1.5rem;">
              <!-- Two Small Slots side by side -->
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; height: 220px;">
                <div style="display: flex; align-items: center; justify-content: center; position: relative; ${styleToString(cardSlotStyle)}">
                  ${faceB64 ? `
                    <img src="${faceB64}" alt="Face" style="width: 100%; height: 100%; object-fit: cover;" />
                  ` : `
                    <span style="${styleToString(slotLabelStyle)}">Face Slot</span>
                  `}
                </div>
                <div style="display: flex; align-items: center; justify-content: center; position: relative; ${styleToString(cardSlotStyle)}">
                  ${profileB64 ? `
                    <img src="${profileB64}" alt="Profile" style="width: 100%; height: 100%; object-fit: cover;" />
                  ` : `
                    <span style="${styleToString(slotLabelStyle)}">Profile Slot</span>
                  `}
                </div>
              </div>

              <!-- Character Stats Display -->
              <div style="flex: 1; display: flex; flex-direction: column; gap: 1rem; justify-content: center;">
                ${[
                  { label: 'HP / Health', value: data.hp },
                  { label: 'Energy / Mana', value: data.energy },
                  { label: 'Combat / Attack', value: data.combat },
                  { label: 'Intellect / Skill', value: data.intellect },
                  { label: 'Agility / Speed', value: data.agility }
                ].map(({ label, value }) => `
                  <div style="display: flex; flex-direction: column; gap: 0.35rem;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">
                      <span>${label}</span>
                      <span>${value}%</span>
                    </div>
                    <div style="width: 100%; height: 12px; background: ${statTrackColor}; border-radius: 6px; overflow: hidden;">
                      <div style="width: ${value}%; height: 100%; background: ${statBarColor}; border-radius: 6px;"></div>
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>
          </div>
        `;
      };

      const renderPortraitHTML = () => {
        const fullBodyB64 = base64Images['full-body'];
        const faceB64 = base64Images['face'];
        const profileB64 = base64Images['profile'];
        
        return `
          <div style="display: flex; flex-direction: column; gap: 2rem; flex: 1; min-height: 0;">
            <!-- Top: Large Full Body Slot -->
            <div style="flex: 1.3; display: flex; align-items: center; justify-content: center; position: relative; min-height: 400px; ${styleToString(cardSlotStyle)}">
              ${fullBodyB64 ? `
                <img src="${fullBodyB64}" alt="Full Body" style="width: 100%; height: 100%; object-fit: cover;" />
              ` : `
                <span style="${styleToString(slotLabelStyle)}">Full Body Slot</span>
              `}
            </div>

            <!-- Middle: Portrait Slots + Stats side by side -->
            <div style="display: grid; grid-template-columns: 1fr 1.2fr; gap: 2rem; flex: 1;">
              <!-- Left Column: Portrait Slots -->
              <div style="display: flex; flex-direction: column; gap: 1rem;">
                <div style="flex: 1; display: flex; align-items: center; justify-content: center; position: relative; min-height: 160px; ${styleToString(cardSlotStyle)}">
                  ${faceB64 ? `
                    <img src="${faceB64}" alt="Face" style="width: 100%; height: 100%; object-fit: cover;" />
                  ` : `
                    <span style="${styleToString(slotLabelStyle)}">Face Slot</span>
                  `}
                </div>
                <div style="flex: 1; display: flex; align-items: center; justify-content: center; position: relative; min-height: 160px; ${styleToString(cardSlotStyle)}">
                  ${profileB64 ? `
                    <img src="${profileB64}" alt="Profile" style="width: 100%; height: 100%; object-fit: cover;" />
                  ` : `
                    <span style="${styleToString(slotLabelStyle)}">Profile Slot</span>
                  `}
                </div>
              </div>

              <!-- Right Column: Stats -->
              <div style="display: flex; flex-direction: column; gap: 0.85rem; justify-content: center;">
                ${[
                  { label: 'HP / Health', value: data.hp },
                  { label: 'Energy / Mana', value: data.energy },
                  { label: 'Combat / Attack', value: data.combat },
                  { label: 'Intellect / Skill', value: data.intellect },
                  { label: 'Agility / Speed', value: data.agility }
                ].map(({ label, value }) => `
                  <div style="display: flex; flex-direction: column; gap: 0.3rem;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.8rem; font-weight: 700; text-transform: uppercase;">
                      <span>${label}</span>
                      <span>${value}%</span>
                    </div>
                    <div style="width: 100%; height: 10px; background: ${statTrackColor}; border-radius: 5px; overflow: hidden;">
                      <div style="width: ${value}%; height: 100%; background: ${statBarColor}; border-radius: 5px;"></div>
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>

            <!-- Bottom: Biography -->
            <div style="height: 140px; display: flex; flex-direction: column; gap: 0.5rem;">
              <span style="${styleToString(slotLabelStyle)}">Biography</span>
              <div class="bio-box" style="flex: 1; padding: 0.8rem; overflow-y: auto; border: ${data.templateId === 'modern-minimal' ? '1px solid #111' : '1px solid rgba(255,255,255,0.08)'}; background: rgba(0,0,0,0.1); border-radius: 4px; ${styleToString(textStyle)}">
                ${data.bio ? data.bio.replace(/\n/g, '<br/>') : 'No biography provided.'}
              </div>
            </div>
          </div>
        `;
      };

      const renderProductionSheetHTML = () => {
        const pData = data.productionData || {};
        const themeColor = data.themeColor || '#cba171';
        
        const renderSlot = (id: string, label: string) => {
          const b64 = base64Images[id];
          return `
            <div style="${styleToString(cardSlotStyle)}; display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; overflow: hidden; width: 100%; height: 100%;">
              ${b64 ? `<img src="${b64}" alt="${label}" style="width: 100%; height: 100%; object-fit: cover;" />` : `<span style="${styleToString(slotLabelStyle)}; opacity: 0.5;">${label}</span>`}
            </div>
          `;
        };

        return `
          <div style="display: flex; flex-direction: column; gap: 2rem; width: 100%; height: 100%;">
            <div style="display: grid; grid-template-columns: 350px 1fr 350px; gap: 2rem;">
              <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                <p style="margin: 0; font-size: 0.9rem; color: ${hexToRgba(themeColor, 0.8)};">AGE: ${pData.age || ''}</p>
                <p style="margin: 0; font-size: 0.9rem; color: ${hexToRgba(themeColor, 0.8)};">HEIGHT: ${pData.height || ''}</p>
                <p style="margin: 0; font-size: 0.9rem; color: ${hexToRgba(themeColor, 0.8)};">WEIGHT: ${pData.weight || ''}</p>
                <p style="margin: 0; font-size: 0.9rem; color: ${hexToRgba(themeColor, 0.8)};">ORIGIN: ${pData.origin || ''}</p>
                <p style="margin: 0; font-size: 0.9rem; color: ${hexToRgba(themeColor, 0.8)};">AFFILIATION: ${pData.affiliation || ''}</p>
                <p style="margin: 0; font-size: 0.9rem; color: ${hexToRgba(themeColor, 0.8)};">STATUS: ${pData.status || ''}</p>
              </div>
              <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 1rem; height: 350px;">
                ${['turnaround-front', 'turnaround-34front', 'turnaround-side', 'turnaround-back', 'turnaround-34back'].map(id => renderSlot(id, id)).join('')}
              </div>
              <div style="display: grid; grid-template-columns: repeat(4, 1fr); grid-template-rows: repeat(2, 1fr); gap: 0.5rem; height: 350px;">
                ${['expr-neutral', 'expr-focus', 'expr-determined', 'expr-alert', 'expr-sad', 'expr-concentrated', 'expr-anxious', 'expr-suspicious'].map(id => renderSlot(id, id)).join('')}
              </div>
            </div>
            <div style="display: grid; grid-template-columns: 200px 1fr 350px; gap: 2rem; flex: 1;">
              <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                <h4 style="${styleToString(slotLabelStyle)}">Equipment Breakdown</h4>
                ${['equip-head', 'equip-torso', 'equip-arms', 'equip-hands', 'equip-legs', 'equip-feet'].map(id => `<div style="height: 60px;">${renderSlot(id, id)}</div>`).join('')}
              </div>
              <div style="display: flex; flex-direction: column; gap: 1rem;">
                <h4 style="${styleToString(slotLabelStyle)}">Equipment & Accessories</h4>
                <div style="display: grid; grid-template-columns: repeat(8, 1fr); gap: 0.5rem; height: 100px;">
                  ${Array.from({length: 8}, (_, i) => renderSlot(`grid-equip-${i+1}`, `Eq ${i+1}`)).join('')}
                </div>
                <h4 style="${styleToString(slotLabelStyle)}">Materials</h4>
                <div style="display: grid; grid-template-columns: repeat(8, 1fr); gap: 0.5rem; height: 80px;">
                  ${Array.from({length: 8}, (_, i) => renderSlot(`mat-${i+1}`, `Mat ${i+1}`)).join('')}
                </div>
                <h4 style="${styleToString(slotLabelStyle)}">Action Poses</h4>
                <div style="display: grid; grid-template-columns: repeat(8, 1fr); gap: 0.5rem; height: 150px;">
                  ${Array.from({length: 8}, (_, i) => renderSlot(`pose-${i+1}`, `Pose ${i+1}`)).join('')}
                </div>
              </div>
              <div style="display: flex; flex-direction: column; gap: 1rem;">
                <h4 style="${styleToString(slotLabelStyle)}">Production Notes</h4>
                <div style="font-size: 0.85rem; color: ${themeColor}; background: ${hexToRgba(themeColor, 0.05)}; padding: 1rem; border: 1px solid ${hexToRgba(themeColor, 0.3)}; flex: 1; overflow-y: auto;">
                  <strong>Overview:</strong><br/>${pData.overview || ''}<br/><br/>
                  <strong>Personality & Motivations:</strong><br/>${pData.personality || ''}<br/><br/>
                  <strong>Competences & Aptitudes:</strong><br/>${pData.competences || ''}<br/><br/>
                  <strong>History & Context:</strong><br/>${pData.history || ''}<br/><br/>
                  <strong>Notes & References:</strong><br/>${pData.notes || ''}
                </div>
              </div>
            </div>
          </div>
        `;
      };

      const htmlContent = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${data.name || 'Character Sheet'} - ${data.role || 'Profile'}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    body {
      margin: 0;
      padding: 2rem;
      background-color: ${data.templateId === 'lina-moreau' ? '#060608' : data.templateId === 'classic-fantasy' ? '#ebdcb9' : '#f0f0f0'};
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
    }
    img {
      max-width: 100%;
      max-height: 100%;
      display: block;
    }
    .bio-box::-webkit-scrollbar {
      width: 6px;
    }
    .bio-box::-webkit-scrollbar-track {
      background: transparent;
    }
    .bio-box::-webkit-scrollbar-thumb {
      background: ${data.templateId === 'lina-moreau' ? 'rgba(0, 240, 255, 0.2)' : 'rgba(0, 0, 0, 0.15)'};
      border-radius: 3px;
    }
  </style>
</head>
<body>
  <div style="${styleToString(containerStyle)}">
    <!-- Header section -->
    <div style="text-align: center; margin-bottom: 2rem;">
      <h1 style="margin: 0; ${styleToString(headerStyle)}">
        ${data.name || 'CHARACTER NAME'}
      </h1>
      <p style="margin: 0.5rem 0 0 0; ${styleToString(roleStyle)}">
        ${data.role || 'ROLE / ARCHETYPE'}
      </p>
    </div>

    <!-- Main Layout -->
    ${customTemplate 
      ? renderCustomHTML()
      : data.templateId === 'production-sheet' 
        ? renderProductionSheetHTML() 
        : (data.orientation === 'landscape' ? renderLandscapeHTML() : renderPortraitHTML())}

    <!-- Custom Portfolio -->
    ${(!customTemplate && data.templateId !== 'production-sheet') ? renderCustomSlotsHTML() : ''}
  </div>
</body>
</html>`;

      const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.download = `${data.name.replace(/\s+/g, '_') || 'character'}_sheet.html`;
      link.href = url;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("HTML Export failed:", err);
      alert("Failed to export offline HTML character sheet.");
    } finally {
      setIsExportingHTML(false);
    }
  };

  // Determine styles based on chosen templateId
  let templateStyle: React.CSSProperties = {};
  let headerStyle: React.CSSProperties = {};
  let roleStyle: React.CSSProperties = {};
  let textStyle: React.CSSProperties = {};
  let slotLabelStyle: React.CSSProperties = {};
  let statBarColor = 'var(--accent)';
  let statTrackColor = 'rgba(255,255,255,0.1)';
  let cardSlotStyle: React.CSSProperties = {};
  let fontClass = 'sans-serif';

  if (data.templateId === 'lina-moreau') {
    // Cyberpunk
    fontClass = 'sans-serif';
    templateStyle = {
      backgroundColor: '#0a0a0f',
      border: '3px solid #00f0ff',
      boxShadow: '0 0 30px rgba(0, 240, 255, 0.25)',
      color: '#fff',
    };
    headerStyle = {
      color: '#ff007f',
      textShadow: '0 0 10px rgba(255, 0, 127, 0.6)',
      textTransform: 'uppercase',
      letterSpacing: '2px',
      fontSize: '3.5rem',
      fontWeight: 800,
    };
    roleStyle = {
      color: '#00f0ff',
      textShadow: '0 0 8px rgba(0, 240, 255, 0.6)',
      textTransform: 'uppercase',
      letterSpacing: '4px',
      fontSize: '1.4rem',
      fontWeight: 700,
    };
    textStyle = {
      color: '#aab0c0',
      fontSize: '1.05rem',
      lineHeight: '1.5',
    };
    slotLabelStyle = {
      color: '#00f0ff',
      fontSize: '0.8rem',
      textTransform: 'uppercase',
      letterSpacing: '1px',
    };
    statBarColor = '#00f0ff';
    statTrackColor = 'rgba(255, 0, 127, 0.15)';
    cardSlotStyle = {
      border: '2px solid rgba(0, 240, 255, 0.4)',
      background: 'rgba(255, 255, 255, 0.02)',
      boxShadow: 'inset 0 0 15px rgba(0, 240, 255, 0.05)',
      borderRadius: '4px',
    };
  } else if (data.templateId === 'classic-fantasy') {
    // Classic Fantasy
    fontClass = 'Georgia, serif';
    templateStyle = {
      backgroundColor: '#f3e5c8',
      backgroundImage: 'radial-gradient(circle, #fbf5e6 0%, #ecdcb9 100%)',
      border: '6px double #5c3d2e',
      color: '#3d2518',
    };
    headerStyle = {
      color: '#5c3d2e',
      fontFamily: 'Georgia, serif',
      fontSize: '3.2rem',
      fontWeight: 700,
      borderBottom: '2px solid #5c3d2e',
      paddingBottom: '0.5rem',
      width: '80%',
      margin: '0 auto 0.5rem auto',
    };
    roleStyle = {
      color: '#8c593b',
      fontFamily: 'Georgia, serif',
      fontStyle: 'italic',
      fontSize: '1.5rem',
      fontWeight: 600,
    };
    textStyle = {
      color: '#4e3629',
      fontSize: '1.1rem',
      lineHeight: '1.6',
    };
    slotLabelStyle = {
      color: '#5c3d2e',
      fontSize: '0.85rem',
      fontWeight: 700,
      textTransform: 'uppercase',
    };
    statBarColor = '#8c593b';
    statTrackColor = 'rgba(92, 61, 46, 0.15)';
    cardSlotStyle = {
      border: '3px solid #5c3d2e',
      background: 'rgba(92, 61, 46, 0.04)',
      boxShadow: '0 4px 10px rgba(0,0,0,0.06)',
      borderRadius: '8px',
    };
  } else if (data.templateId === 'production-sheet') {
    const themeColor = data.themeColor || '#cba171';

    fontClass = 'Outfit, sans-serif';
    templateStyle = {
      backgroundColor: '#11151c',
      border: `4px solid ${themeColor}`,
      color: themeColor,
    };
    headerStyle = {
      color: themeColor,
      textTransform: 'uppercase',
      fontSize: '3.6rem',
      fontWeight: 900,
      letterSpacing: '2px',
    };
    roleStyle = {
      color: hexToRgba(themeColor, 0.8),
      textTransform: 'uppercase',
      letterSpacing: '2px',
      fontSize: '1.2rem',
      fontWeight: 500,
    };
    textStyle = {
      color: themeColor,
      fontSize: '1rem',
      lineHeight: '1.5',
    };
    slotLabelStyle = {
      color: themeColor,
      fontSize: '0.8rem',
      fontWeight: 900,
      textTransform: 'uppercase',
    };
    statBarColor = themeColor;
    statTrackColor = '#222831';
    cardSlotStyle = {
      border: `1px solid ${themeColor}`,
      borderRadius: '2px',
      background: hexToRgba(themeColor, 0.05),
    };
  } else {
    // Modern Minimalist
    fontClass = 'system-ui, -apple-system, sans-serif';
    templateStyle = {
      backgroundColor: '#ffffff',
      border: '4px solid #111',
      color: '#111',
    };
    headerStyle = {
      color: '#111',
      textTransform: 'uppercase',
      fontSize: '3.6rem',
      fontWeight: 900,
      letterSpacing: '-1px',
    };
    roleStyle = {
      color: '#666',
      textTransform: 'uppercase',
      letterSpacing: '2px',
      fontSize: '1.2rem',
      fontWeight: 500,
    };
    textStyle = {
      color: '#333',
      fontSize: '1rem',
      lineHeight: '1.5',
    };
    slotLabelStyle = {
      color: '#111',
      fontSize: '0.8rem',
      fontWeight: 900,
      textTransform: 'uppercase',
    };
    statBarColor = '#111111';
    statTrackColor = '#e5e5e5';
    cardSlotStyle = {
      border: '2px solid #111',
      borderRadius: '0px',
      background: '#fafafa',
    };
  }

  const renderCustomTemplateJSX = () => {
    if (!customTemplate) return null;
    return (
      <div style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '600px',
        backgroundImage: `url(${customTemplate.backgroundImage})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        border: '3px solid var(--accent)',
        borderRadius: '8px',
        overflow: 'hidden'
      }}>
        {customTemplate.slots.map((slot: any) => {
          const b64 = data.images[slot.id];
          const isBio = slot.id === 'bio' || slot.label.toLowerCase() === 'biography' || slot.label.toLowerCase() === 'bio';
          const isStats = slot.id === 'stats' || slot.label.toLowerCase() === 'stats' || slot.label.toLowerCase() === 'statistics';
          
          return (
            <div 
              key={slot.id} 
              onClick={() => onSlotSelect?.(slot.id)}
              style={{
                position: 'absolute',
                left: `${slot.x}%`,
                top: `${slot.y}%`,
                width: `${slot.w}%`,
                height: `${slot.h}%`,
                cursor: 'pointer',
                boxSizing: 'border-box',
                zIndex: 10,
                ...cardSlotStyle
              }}
            >
              {isBio ? (
                <div className="bio-box" style={{ padding: '0.5rem', width: '100%', height: '100%', overflowY: 'auto', fontSize: '0.85rem', ...textStyle, background: 'rgba(0,0,0,0.6)' }}>
                  <strong>Biography</strong>
                  <p style={{ margin: '0.2rem 0 0 0', whiteSpace: 'pre-wrap' }}>{data.bio || 'No biography provided.'}</p>
                </div>
              ) : isStats ? (
                <div style={{ padding: '0.5rem', width: '100%', height: '100%', display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.75rem', justifyContent: 'center', background: 'rgba(0,0,0,0.6)', overflowY: 'auto' }}>
                  {[
                    { label: 'HP', value: data.hp },
                    { label: 'Energy', value: data.energy },
                    { label: 'Combat', value: data.combat },
                    { label: 'Intellect', value: data.intellect },
                    { label: 'Agility', value: data.agility }
                  ].map(({ label, value }) => (
                    <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: '0.1rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 'bold' }}>
                        <span>{label}</span>
                        <span>{value}%</span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: statTrackColor, borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{ width: `${value}%`, height: '100%', background: statBarColor }} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : b64 ? (
                <img src={b64} alt={slot.label} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', background: 'rgba(0,0,0,0.4)', color: 'var(--accent)', fontWeight: 'bold', fontSize: '0.85rem', padding: '0.2rem', textAlign: 'center' }}>
                  {slot.label}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const renderAssetPortfolio = () => {
    const customSlots = data.slots.filter(s => s.id !== 'face' && s.id !== 'profile' && s.id !== 'full-body');
    if (customSlots.length === 0) return null;
    
    return (
      <div style={{ 
        marginTop: '2.5rem', 
        borderTop: data.templateId === 'modern-minimal' ? '2px solid #111' : '1px solid rgba(255, 255, 255, 0.1)', 
        paddingTop: '1.5rem',
        width: '100%'
      }}>
        <h3 style={{ 
          margin: '0 0 1.5rem 0', 
          fontSize: '1.4rem', 
          textTransform: 'uppercase', 
          letterSpacing: '2px',
          textAlign: 'center',
          color: data.templateId === 'lina-moreau' ? '#00f0ff' : data.templateId === 'classic-fantasy' ? '#5c3d2e' : '#111',
          textShadow: data.templateId === 'lina-moreau' ? '0 0 8px rgba(0, 240, 255, 0.4)' : undefined,
          fontFamily: fontClass
        }}>
          Character Asset Portfolio
        </h3>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(3, 1fr)', 
          gap: '1.5rem',
          width: '100%'
        }}>
          {customSlots.map(slot => (
            <div key={slot.id} style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', alignItems: 'center' }}>
              <div style={{ 
                width: '100%',
                aspectRatio: slot.aspect ? String(slot.aspect) : '1', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center', 
                position: 'relative',
                overflow: 'hidden',
                minHeight: '160px',
                boxSizing: 'border-box',
                ...cardSlotStyle 
              }}>
                {data.images[slot.id] ? (
                  <img src={data.images[slot.id]} alt={slot.label} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                ) : (
                  <span style={{ ...slotLabelStyle, fontSize: '0.85rem', textAlign: 'center', padding: '0.5rem' }}>{slot.label}</span>
                )}
              </div>
              <span style={{ 
                fontSize: '0.85rem', 
                fontWeight: 700, 
                textTransform: 'uppercase', 
                textAlign: 'center',
                color: data.templateId === 'lina-moreau' ? '#ff007f' : data.templateId === 'classic-fantasy' ? '#8c593b' : '#666'
              }}>
                {slot.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderProductionSheetJSX = () => {
    const pData = data.productionData || {};
    const themeColor = data.themeColor || '#cba171';
    
    const renderSlotJSX = (id: string, label: string) => {
      const b64 = data.images[id];
      return (
        <div key={id} onClick={() => onSlotSelect?.(id)} style={{ ...cardSlotStyle, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', position: 'relative', overflow: 'hidden', width: '100%', height: '100%', cursor: onSlotSelect ? 'pointer' : 'default' }}>
          {b64 ? <img src={b64} alt={label} style={{ width: '100%', height: '100%', objectFit: 'contain' }} /> : <span style={{ ...slotLabelStyle, opacity: 0.5 }}>{label}</span>}
        </div>
      );
    };

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', width: '100%', height: '100%' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '350px 1fr 350px', gap: '2rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <p style={{ margin: 0, fontSize: '0.9rem', color: themeColor, opacity: 0.8 }}>AGE: {pData.age || ''}</p>
            <p style={{ margin: 0, fontSize: '0.9rem', color: themeColor, opacity: 0.8 }}>HEIGHT: {pData.height || ''}</p>
            <p style={{ margin: 0, fontSize: '0.9rem', color: themeColor, opacity: 0.8 }}>WEIGHT: {pData.weight || ''}</p>
            <p style={{ margin: 0, fontSize: '0.9rem', color: themeColor, opacity: 0.8 }}>ORIGIN: {pData.origin || ''}</p>
            <p style={{ margin: 0, fontSize: '0.9rem', color: themeColor, opacity: 0.8 }}>AFFILIATION: {pData.affiliation || ''}</p>
            <p style={{ margin: 0, fontSize: '0.9rem', color: themeColor, opacity: 0.8 }}>STATUS: {pData.status || ''}</p>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1rem', height: '350px' }}>
            {['turnaround-front', 'turnaround-34front', 'turnaround-side', 'turnaround-back', 'turnaround-34back'].map(id => renderSlotJSX(id, id))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gridTemplateRows: 'repeat(2, 1fr)', gap: '0.5rem', height: '350px' }}>
            {['expr-neutral', 'expr-focus', 'expr-determined', 'expr-alert', 'expr-sad', 'expr-concentrated', 'expr-anxious', 'expr-suspicious'].map(id => renderSlotJSX(id, id))}
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 350px', gap: '2rem', flex: 1 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <h4 style={slotLabelStyle}>Equipment Breakdown</h4>
            {['equip-head', 'equip-torso', 'equip-arms', 'equip-hands', 'equip-legs', 'equip-feet'].map(id => <div key={id} style={{ height: '60px' }}>{renderSlotJSX(id, id)}</div>)}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <h4 style={slotLabelStyle}>Equipment & Accessories</h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: '0.5rem', height: '100px' }}>
              {Array.from({length: 8}, (_, i) => renderSlotJSX(`grid-equip-${i+1}`, `Eq ${i+1}`))}
            </div>
            <h4 style={slotLabelStyle}>Materials</h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: '0.5rem', height: '80px' }}>
              {Array.from({length: 8}, (_, i) => renderSlotJSX(`mat-${i+1}`, `Mat ${i+1}`))}
            </div>
            <h4 style={slotLabelStyle}>Action Poses</h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: '0.5rem', height: '150px' }}>
              {Array.from({length: 8}, (_, i) => renderSlotJSX(`pose-${i+1}`, `Pose ${i+1}`))}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <h4 style={slotLabelStyle}>Production Notes</h4>
            <div style={{ fontSize: '0.85rem', color: themeColor, background: 'rgba(255,255,255,0.03)', padding: '1rem', border: `1px solid ${themeColor}`, opacity: 0.8, flex: 1, overflowY: 'auto' }}>
              <strong>Overview:</strong><br/>{pData.overview || ''}<br/><br/>
              <strong>Personality & Motivations:</strong><br/>{pData.personality || ''}<br/><br/>
              <strong>Competences & Aptitudes:</strong><br/>{pData.competences || ''}<br/><br/>
              <strong>History & Context:</strong><br/>{pData.history || ''}<br/><br/>
              <strong>Notes & References:</strong><br/>{pData.notes || ''}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="sheet-panel-right" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem', overflowY: 'auto', backgroundColor: 'var(--bg-secondary)', fontFamily: 'Outfit, sans-serif', color: 'var(--text-main)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, letterSpacing: '-0.02em', background: 'linear-gradient(to right, #fff, #aaa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Live Preview</h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button 
            onClick={() => updateData({ orientation: data.orientation === 'portrait' ? 'landscape' : 'portrait' })}
            style={{ 
              padding: '0.5rem 0.8rem', 
              cursor: 'pointer', 
              background: 'var(--bg-main)', 
              border: '1px solid var(--border-color)', 
              borderRadius: '6px', 
              color: 'var(--text-secondary)',
              fontSize: '0.8rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem'
            }}
          >
            Rotate ({data.orientation === 'landscape' ? 'Landscape' : 'Portrait'})
          </button>
          <button 
            onClick={handleExport}
            style={{ 
              padding: '0.5rem 0.8rem', 
              cursor: 'pointer', 
              background: 'linear-gradient(135deg, var(--accent), #5a4bcf)', 
              border: 'none', 
              borderRadius: '6px', 
              color: 'white',
              fontSize: '0.8rem',
              fontWeight: 600,
              boxShadow: '0 4px 12px var(--accent-glow)'
            }}
          >
            Export PNG
          </button>
          <button 
            onClick={handleExportHTML}
            disabled={isExportingHTML}
            style={{ 
              padding: '0.5rem 0.8rem', 
              cursor: 'pointer', 
              background: 'linear-gradient(135deg, #10b981, #059669)', 
              border: 'none', 
              borderRadius: '6px', 
              color: 'white',
              fontSize: '0.8rem',
              fontWeight: 600,
              boxShadow: '0 4px 12px rgba(16, 185, 129, 0.25)',
              opacity: isExportingHTML ? 0.6 : 1
            }}
          >
            {isExportingHTML ? 'Exporting...' : 'Export HTML'}
          </button>
        </div>
      </div>
      
      {/* Container holding scaled template preview */}
      <div style={{ 
        width: '100%', 
        overflowX: 'auto', 
        overflowY: 'auto',
        display: 'flex', 
        justifyContent: 'center', 
        padding: '1rem',
        background: 'var(--bg-main)',
        borderRadius: '12px',
        border: '1px solid var(--border-color)',
        minHeight: '620px',
        alignItems: 'flex-start'
      }}>
        <div className="preview-container-wrapper" style={{
          width: '100%',
          maxWidth: data.orientation === 'landscape' ? '600px' : '400px',
          height: `${previewHeight * 0.5}px`,
          position: 'relative',
          overflow: 'hidden',
          borderRadius: '4px',
          transition: 'height 0.2s ease-in-out',
        }}>
          <div 
            id="character-template-preview" 
            className={`preview-scale-${data.templateId === 'production-sheet' ? 'production' : data.orientation}`}
            style={{
              width: data.templateId === 'production-sheet' ? '2000px' : (data.orientation === 'landscape' ? '1200px' : '800px'),
              minHeight: data.templateId === 'production-sheet' ? '1200px' : (data.orientation === 'landscape' ? '800px' : '1200px'),
              height: 'auto',
              position: 'absolute',
              top: 0,
              left: 0,
              transformOrigin: 'top left',
              display: 'flex',
              flexDirection: 'column',
              padding: '2.5rem',
              boxSizing: 'border-box',
              fontFamily: fontClass,
              ...templateStyle
            }}
          >
            {/* Header section */}
            <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
              <h1 style={{ margin: 0, ...headerStyle }}>
                {data.name || 'CHARACTER NAME'}
              </h1>
              <p style={{ margin: '0.5rem 0 0 0', ...roleStyle }}>
                {data.role || 'ROLE / ARCHETYPE'}
              </p>
            </div>
            
            {/* Layout based on orientation */}
            {customTemplate ? renderCustomTemplateJSX() : data.templateId === 'production-sheet' ? renderProductionSheetJSX() : data.orientation === 'landscape' ? (
              <>
                {/* LANDSCAPE MODE GRID */}
                <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '2.5rem', flex: 1, minHeight: 0 }}>
                {/* Left Side: Body Slot + Biography */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                  <div onClick={() => onSlotSelect?.('full-body')} style={{ 
                    flex: 1, 
                    display: 'flex', 
                    flexDirection: 'column', 
                    alignItems: 'center', 
                    justifyContent: 'center', 
                    position: 'relative',
                    minHeight: '340px',
                    cursor: onSlotSelect ? 'pointer' : 'default',
                    ...cardSlotStyle 
                  }}>
                    {data.images['full-body'] ? (
                      <img src={data.images['full-body']} alt="Full Body" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                    ) : (
                      <span style={slotLabelStyle}>Full Body Slot</span>
                    )}
                  </div>
                  <div style={{ height: '150px', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    <span style={{ ...slotLabelStyle, fontSize: '0.9rem' }}>Biography</span>
                    <div style={{ 
                      flex: 1, 
                      padding: '0.8rem', 
                      overflowY: 'auto', 
                      border: data.templateId === 'modern-minimal' ? '1px solid #111' : '1px solid rgba(255,255,255,0.08)',
                      background: 'rgba(0,0,0,0.1)',
                      borderRadius: '4px',
                      ...textStyle 
                    }}>
                      {data.bio || 'Enter a biography in the sidebar controls.'}
                    </div>
                  </div>
                </div>
                
                {/* Right Side: Portrait Slots + Stats */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                  {/* Two Small Slots side by side */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', height: '220px' }}>
                    <div onClick={() => onSlotSelect?.('face')} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', cursor: onSlotSelect ? 'pointer' : 'default', ...cardSlotStyle }}>
                      {data.images['face'] ? (
                        <img src={data.images['face']} alt="Face" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                      ) : (
                        <span style={slotLabelStyle}>Face Slot</span>
                      )}
                    </div>
                    <div onClick={() => onSlotSelect?.('profile')} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', cursor: onSlotSelect ? 'pointer' : 'default', ...cardSlotStyle }}>
                      {data.images['profile'] ? (
                        <img src={data.images['profile']} alt="Profile" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                      ) : (
                        <span style={slotLabelStyle}>Profile Slot</span>
                      )}
                    </div>
                  </div>

                  {/* Character Stats Display */}
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem', justifyContent: 'center' }}>
                    {[
                      { label: 'HP / Health', value: data.hp },
                      { label: 'Energy / Mana', value: data.energy },
                      { label: 'Combat / Attack', value: data.combat },
                      { label: 'Intellect / Skill', value: data.intellect },
                      { label: 'Agility / Speed', value: data.agility }
                    ].map(({ label, value }) => (
                      <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          <span>{label}</span>
                          <span>{value}%</span>
                        </div>
                        <div style={{ width: '100%', height: '12px', background: statTrackColor, borderRadius: '6px', overflow: 'hidden' }}>
                          <div style={{ width: `${value}%`, height: '100%', background: statBarColor, borderRadius: '6px', transition: 'width 0.3s ease' }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              {!customTemplate && data.templateId !== 'production-sheet' ? renderAssetPortfolio() : null}
              </>
            ) : (
              // PORTRAIT MODE GRID
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', flex: 1, minHeight: 0 }}>
                {/* Top: Large Full Body Slot */}
                <div onClick={() => onSlotSelect?.('full-body')} style={{ 
                  flex: 1.3, 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center', 
                  position: 'relative',
                  minHeight: '400px',
                  cursor: onSlotSelect ? 'pointer' : 'default',
                  ...cardSlotStyle 
                }}>
                  {data.images['full-body'] ? (
                    <img src={data.images['full-body']} alt="Full Body" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                  ) : (
                    <span style={slotLabelStyle}>Full Body Slot</span>
                  )}
                </div>

                {/* Middle: Portrait Slots + Stats side by side */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '2rem', flex: 1 }}>
                  {/* Left Column: Portrait Slots */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div onClick={() => onSlotSelect?.('face')} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', minHeight: '160px', cursor: onSlotSelect ? 'pointer' : 'default', ...cardSlotStyle }}>
                      {data.images['face'] ? (
                        <img src={data.images['face']} alt="Face" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                      ) : (
                        <span style={slotLabelStyle}>Face Slot</span>
                      )}
                    </div>
                    <div onClick={() => onSlotSelect?.('profile')} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', minHeight: '160px', cursor: onSlotSelect ? 'pointer' : 'default', ...cardSlotStyle }}>
                      {data.images['profile'] ? (
                        <img src={data.images['profile']} alt="Profile" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                      ) : (
                        <span style={slotLabelStyle}>Profile Slot</span>
                      )}
                    </div>
                  </div>

                  {/* Right Column: Stats */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', justifyContent: 'center' }}>
                    {[
                      { label: 'HP / Health', value: data.hp },
                      { label: 'Energy / Mana', value: data.energy },
                      { label: 'Combat / Attack', value: data.combat },
                      { label: 'Intellect / Skill', value: data.intellect },
                      { label: 'Agility / Speed', value: data.agility }
                    ].map(({ label, value }) => (
                      <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase' }}>
                          <span>{label}</span>
                          <span>{value}%</span>
                        </div>
                        <div style={{ width: '100%', height: '10px', background: statTrackColor, borderRadius: '5px', overflow: 'hidden' }}>
                          <div style={{ width: `${value}%`, height: '100%', background: statBarColor, borderRadius: '5px', transition: 'width 0.3s ease' }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Bottom: Biography */}
                <div style={{ height: '140px', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <span style={slotLabelStyle}>Biography</span>
                  <div style={{ 
                    flex: 1, 
                    padding: '0.8rem', 
                    overflowY: 'auto', 
                    border: data.templateId === 'modern-minimal' ? '1px solid #111' : '1px solid rgba(255,255,255,0.08)',
                    background: 'rgba(0,0,0,0.1)',
                    borderRadius: '4px',
                    ...textStyle 
                  }}>
                    {data.bio || 'Enter a biography in the sidebar controls.'}
                  </div>
                </div>
                {!customTemplate && data.templateId !== 'production-sheet' ? renderAssetPortfolio() : null}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
