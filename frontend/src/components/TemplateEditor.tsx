import React, { useState, useEffect, useRef } from 'react';
import { Image as ImageIcon, Wand2, Plus, Save, MousePointer2 } from 'lucide-react';

interface Slot {
  id: string;
  x: number; // percentage (0 - 100)
  y: number; // percentage (0 - 100)
  w: number; // percentage (0 - 100)
  h: number; // percentage (0 - 100)
  label: string;
}

interface TemplateEditorProps {
  characterData?: any;
  updateCharacterData?: (updates: any) => void;
}

export function TemplateEditor({ characterData, updateCharacterData }: TemplateEditorProps) {
  const [rawTemplates, setRawTemplates] = useState<string[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  
  const [mode, setMode] = useState<'select' | 'erase'>('select');
  const [slots, setSlots] = useState<Slot[]>([]);
  const [activeSlotId, setActiveSlotId] = useState<string | null>(null);

  // Dragging and Resizing State
  const [draggedSlotId, setDraggedSlotId] = useState<string | null>(null);
  const [resizedSlotId, setResizedSlotId] = useState<string | null>(null);
  const [dragStart, setDragStart] = useState<{
    mouseX: number;
    mouseY: number;
    x: number;
    y: number;
    w: number;
    h: number;
  } | null>(null);
  
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [brushSize, setBrushSize] = useState(20);
  
  // Load templates list
  useEffect(() => {
    fetch('/api/studio/templates/raw')
      .then(res => res.json())
      .then(data => {
        if (data.images) setRawTemplates(data.images);
      })
      .catch(err => console.error(err));
  }, []);

  const initCanvas = (imgUrl: string) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const img = new Image();
    img.crossOrigin = "Anonymous";
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
    };
    img.src = imgUrl;
  };

  useEffect(() => {
    if (selectedTemplate) {
      initCanvas(`/api/studio/templates/raw/${selectedTemplate}`);
      setSlots([]); // reset custom slots for new template
      setActiveSlotId(null);
    }
  }, [selectedTemplate]);

  // Global mouse up to release drags/resizes safely
  useEffect(() => {
    const handleGlobalMouseUp = () => {
      setDraggedSlotId(null);
      setResizedSlotId(null);
      setDragStart(null);
    };
    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => window.removeEventListener('mouseup', handleGlobalMouseUp);
  }, []);

  // Drawing logic for the erase mask
  const startDrawing = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (mode !== 'erase') return;
    setIsDrawing(true);
    draw(e);
  };
  
  const stopDrawing = () => {
    setIsDrawing(false);
  };
  
  const draw = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing || mode !== 'erase') return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;
    
    ctx.fillStyle = 'rgba(255, 0, 0, 0.5)'; // Semi-transparent red for mask
    ctx.beginPath();
    ctx.arc(x, y, brushSize, 0, Math.PI * 2);
    ctx.fill();
  };

  const handleInpaintErase = async () => {
    alert("Inpainting API call to ComfyUI would execute here using the drawn red mask.");
  };

  const addSlot = () => {
    const newId = `slot_${Date.now()}`;
    setSlots([...slots, { id: newId, x: 10, y: 10, w: 20, h: 25, label: 'New Slot' }]);
    setActiveSlotId(newId);
  };

  const handleSlotMouseDown = (e: React.MouseEvent, slotId: string) => {
    e.stopPropagation();
    if (mode === 'erase') return;
    setActiveSlotId(slotId);
    setDraggedSlotId(slotId);
    const slot = slots.find(s => s.id === slotId);
    if (slot) {
      setDragStart({
        mouseX: e.clientX,
        mouseY: e.clientY,
        x: slot.x,
        y: slot.y,
        w: slot.w,
        h: slot.h
      });
    }
  };

  const handleResizeMouseDown = (e: React.MouseEvent, slotId: string) => {
    e.stopPropagation();
    e.preventDefault();
    if (mode === 'erase') return;
    setActiveSlotId(slotId);
    setResizedSlotId(slotId);
    const slot = slots.find(s => s.id === slotId);
    if (slot) {
      setDragStart({
        mouseX: e.clientX,
        mouseY: e.clientY,
        x: slot.x,
        y: slot.y,
        w: slot.w,
        h: slot.h
      });
    }
  };

  const handleContainerMouseMove = (e: React.MouseEvent) => {
    if (!dragStart || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    
    // Calculate mouse delta in percentages relative to editor preview container size
    const dxPct = ((e.clientX - dragStart.mouseX) / rect.width) * 100;
    const dyPct = ((e.clientY - dragStart.mouseY) / rect.height) * 100;

    if (draggedSlotId) {
      setSlots(prev => prev.map(s => {
        if (s.id === draggedSlotId) {
          const newX = Math.max(0, Math.min(100 - s.w, dragStart.x + dxPct));
          const newY = Math.max(0, Math.min(100 - s.h, dragStart.y + dyPct));
          return { ...s, x: newX, y: newY };
        }
        return s;
      }));
    } else if (resizedSlotId) {
      setSlots(prev => prev.map(s => {
        if (s.id === resizedSlotId) {
          const newW = Math.max(5, Math.min(100 - s.x, dragStart.w + dxPct));
          const newH = Math.max(5, Math.min(100 - s.y, dragStart.h + dyPct));
          return { ...s, w: newW, h: newH };
        }
        return s;
      }));
    }
  };

  const handleSaveTemplate = () => {
    if (!selectedTemplate) {
      alert("Please select a template image first!");
      return;
    }
    const templateName = window.prompt("Template Name", selectedTemplate.replace(/\.[^/.]+$/, "") + " Custom Layout");
    if (!templateName) return;

    const templateId = `custom-template-${Date.now()}`;
    const customTemplate = {
      id: templateId,
      label: templateName,
      backgroundImage: `/api/studio/templates/raw/${selectedTemplate}`,
      slots: slots.map(s => ({
        id: s.id,
        label: s.label,
        x: s.x,
        y: s.y,
        w: s.w,
        h: s.h
      }))
    };

    // Save to localStorage list of custom templates
    const existingRaw = localStorage.getItem('mklan_custom_templates');
    const existing = existingRaw ? JSON.parse(existingRaw) : [];
    existing.push(customTemplate);
    localStorage.setItem('mklan_custom_templates', JSON.stringify(existing));

    // Update parent character sheet data if hooks/props are passed
    if (characterData && updateCharacterData) {
      updateCharacterData({
        templateId: templateId,
        slots: slots.map(s => ({
          id: s.id,
          label: s.label,
          aspect: s.w / s.h
        }))
      });
      alert(`Template "${templateName}" saved successfully and set as active layout!`);
    } else {
      alert(`Template "${templateName}" saved successfully!`);
    }
  };

  return (
    <div style={{ padding: '1rem', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Wand2 size={20} /> Template Editor
        </h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <select 
            value={selectedTemplate || ''} 
            onChange={e => setSelectedTemplate(e.target.value)}
            style={{ padding: '0.5rem', background: 'var(--bg-main)', border: '1px solid var(--border-color)', color: '#fff', borderRadius: '4px' }}
          >
            <option value="">-- Select Raw Template --</option>
            {rawTemplates.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <button onClick={handleInpaintErase} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 1rem', background: 'var(--accent)', border: 'none', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}>
            <Wand2 size={16} /> Erase Masked Area
          </button>
          <button onClick={addSlot} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.1)', border: '1px solid var(--border-color)', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}>
            <Plus size={16} /> Add Slot
          </button>
          <button onClick={handleSaveTemplate} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.1)', border: '1px solid var(--border-color)', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}>
            <Save size={16} /> Save Template
          </button>
        </div>
      </div>
      
      {/* Editor Controls */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', alignItems: 'center' }}>
        <button 
          onClick={() => setMode('select')}
          style={{ padding: '0.5rem', background: mode === 'select' ? 'var(--accent)' : 'var(--bg-main)', border: '1px solid var(--border-color)', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}
        >
          <MousePointer2 size={16} /> Move & Size Slots
        </button>
        <button 
          onClick={() => setMode('erase')}
          style={{ padding: '0.5rem', background: mode === 'erase' ? 'var(--accent)' : 'var(--bg-main)', border: '1px solid var(--border-color)', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}
        >
          <Wand2 size={16} /> Erase Mask (Draw)
        </button>
        {mode === 'erase' && (
          <input 
            type="range" min="5" max="100" value={brushSize} onChange={e => setBrushSize(parseInt(e.target.value))}
            style={{ width: '100px' }}
          />
        )}
      </div>

      {/* Selected Slot Options Manager */}
      {activeSlotId && (
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem', padding: '0.8rem', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-color)', borderRadius: '6px' }}>
          <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Active Slot:</span>
          
          <input 
            type="text" 
            value={slots.find(s => s.id === activeSlotId)?.label || ''} 
            onChange={e => {
              const val = e.target.value;
              setSlots(prev => prev.map(s => s.id === activeSlotId ? { ...s, label: val } : s));
            }}
            placeholder="e.g. Face, Weapon, Biography, Stats"
            style={{ padding: '0.4rem', background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: '4px', color: '#fff', fontSize: '0.8rem', outline: 'none' }}
          />

          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Presets:</span>
          {['Face', 'Profile', 'Full Body', 'Biography', 'Stats'].map(preset => (
            <button
              key={preset}
              onClick={() => {
                setSlots(prev => prev.map(s => {
                  if (s.id === activeSlotId) {
                    const presetId = preset.toLowerCase().replace(' ', '-');
                    return { ...s, id: presetId, label: preset };
                  }
                  return s;
                }));
                // update activeSlotId in case we changed its id
                const presetId = preset.toLowerCase().replace(' ', '-');
                setActiveSlotId(presetId);
              }}
              style={{ padding: '0.2rem 0.5rem', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: '#bbb', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}
            >
              {preset}
            </button>
          ))}

          <button 
            onClick={() => {
              setSlots(prev => prev.filter(s => s.id !== activeSlotId));
              setActiveSlotId(null);
            }}
            style={{ marginLeft: 'auto', padding: '0.4rem 0.8rem', background: 'rgba(255,87,87,0.1)', border: '1px solid rgba(255,87,87,0.3)', color: 'var(--danger)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem' }}
          >
            Delete Slot
          </button>
        </div>
      )}

      {/* Editor Canvas Container */}
      <div 
        ref={containerRef}
        onMouseMove={handleContainerMouseMove}
        style={{ flex: 1, border: '1px solid var(--border-color)', background: '#111', overflow: 'auto', position: 'relative' }}
      >
        {!selectedTemplate ? (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>
            <ImageIcon size={48} style={{ opacity: 0.5, marginBottom: '1rem' }} />
            <p>Select a raw template image to begin editing.</p>
          </div>
        ) : (
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <canvas
              ref={canvasRef}
              onMouseDown={startDrawing}
              onMouseUp={stopDrawing}
              onMouseLeave={stopDrawing}
              onMouseMove={draw}
              style={{ display: 'block', cursor: mode === 'erase' ? 'crosshair' : 'default', maxWidth: '100%', height: 'auto' }}
            />
            {/* Render absolute-positioned draggable slots */}
            {mode !== 'erase' && slots.map((slot) => (
              <div 
                key={slot.id}
                onMouseDown={(e) => handleSlotMouseDown(e, slot.id)}
                style={{
                  position: 'absolute',
                  left: `${slot.x}%`,
                  top: `${slot.y}%`,
                  width: `${slot.w}%`,
                  height: `${slot.h}%`,
                  border: activeSlotId === slot.id ? '2px solid #00f0ff' : '2px dashed rgba(0, 240, 255, 0.6)',
                  boxShadow: activeSlotId === slot.id ? '0 0 10px rgba(0, 240, 255, 0.4)' : 'none',
                  background: activeSlotId === slot.id ? 'rgba(0, 240, 255, 0.25)' : 'rgba(0, 240, 255, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fff',
                  fontWeight: 'bold',
                  textShadow: '0 1px 3px rgba(0,0,0,0.8)',
                  cursor: 'move',
                  userSelect: 'none',
                  zIndex: activeSlotId === slot.id ? 20 : 10
                }}
              >
                <span style={{ fontSize: '0.85rem', padding: '0.3rem', textAlign: 'center' }}>{slot.label}</span>
                
                {/* Drag Resize Handle (se-resize) in Bottom-Right Corner */}
                <div 
                  onMouseDown={(e) => handleResizeMouseDown(e, slot.id)}
                  style={{
                    position: 'absolute',
                    right: 0,
                    bottom: 0,
                    width: '12px',
                    height: '12px',
                    background: '#00f0ff',
                    cursor: 'se-resize',
                    zIndex: 30
                  }}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
