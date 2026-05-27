import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactCrop, { type Crop, centerCrop, makeAspectCrop } from 'react-image-crop';
import 'react-image-crop/dist/ReactCrop.css';
import html2canvas from 'html2canvas';
import { captureTemplateForControlNet } from '../utils/captureTemplate';

interface Props {
  slots: { id: string; label: string; aspect?: number }[];
  onAssignSlot: (slotId: string, imageB64: string) => void;
  activeSlotId?: string;
  onSlotSelect?: (slotId: string) => void;
  onImageGenerated?: (assetId: string) => void;
  reopenImageB64?: string | null;
  onReopenComplete?: () => void;
}

export function ImageGeneratorCropper({ slots, onAssignSlot, activeSlotId, onSlotSelect, onImageGenerated, reopenImageB64, onReopenComplete }: Props) {
  // Main settings
  const [prompt, setPrompt] = useState('A futuristic sci-fi character portrait, cyberpunk aesthetic, high detail neon lighting');
  const [negativePrompt, setNegativePrompt] = useState('ugly, blurry, low quality, deformed');
  const [inferenceMode, setInferenceMode] = useState<'diffusers' | 'comfyui'>('diffusers');
  const [models, setModels] = useState<{ name: string; path: string; provider: string }[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  
  // Advanced parameters
  const [resolution, setResolution] = useState<string>('1024x1024');
  const [steps, setSteps] = useState<number>(30);
  const [cfgScale, setCfgScale] = useState<number>(7.0);
  const [sampler, setSampler] = useState<string>('Euler a');
  const [scheduler, setScheduler] = useState<string>('Automatic');
  const [seed, setSeed] = useState<string>('');
  
  // ControlNet settings
  const [controlNetEnabled, setControlNetEnabled] = useState<boolean>(false);
  const [controlNetType, setControlNetType] = useState<string>('canny');
  const [controlNetStrength, setControlNetStrength] = useState<number>(0.8);
  const [controlNetSource, setControlNetSource] = useState<'template' | 'custom'>('template');
  const [customControlNetImage, setCustomControlNetImage] = useState<string | null>(null);

  const [comfySamplers, setComfySamplers] = useState<string[]>(['Euler a', 'DPM++ 2M', 'DPM++ SDE', 'LCM', 'kl-optimal']);
  const [comfySchedulers, setComfySchedulers] = useState<string[]>(['Automatic', 'Normal', 'Karras', 'Exponential', 'gits']);
  const [comfyControlNets, setComfyControlNets] = useState<string[]>(['canny', 'openpose', 'depthanything', 'scribble', 'lineart']);

  const [controlNetPreviewMap, setControlNetPreviewMap] = useState<string | null>(null);
  const [isPreprocessing, setIsPreprocessing] = useState<boolean>(false);

  const [generatedImg, setGeneratedImg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [crop, setCrop] = useState<Crop>();
  const internalSelectedSlotId = useState(slots[0]?.id || 'face')[0];
  const selectedSlotId = activeSlotId || internalSelectedSlotId;
  const selectedSlot = slots.find(s => s.id === selectedSlotId);
  const [aspect, setAspect] = useState<number | undefined>(selectedSlot ? selectedSlot.aspect : 1);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isRemovingBg, setIsRemovingBg] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const imgRef = useRef<HTMLImageElement>(null);

  // Sync aspect when slot changes externally
  useEffect(() => {
    if (selectedSlot) {
      setAspect(selectedSlot.aspect);
    }
  }, [selectedSlot]);

  // Handle reopen image
  useEffect(() => {
    if (reopenImageB64) {
      setGeneratedImg(reopenImageB64);
      onReopenComplete?.();
    }
  }, [reopenImageB64, onReopenComplete]);

  // Fetch checkpoints/models on mount
  useEffect(() => {
    fetch('/api/studio/models')
      .then(res => res.json())
      .then(data => {
        if (data && Array.isArray(data.models)) {
          setModels(data.models);
        }
      })
      .catch(err => console.error("Error fetching models:", err));
  }, []);

  // Fetch ComfyUI dynamic options (samplers, schedulers, controlnets) when in ComfyUI mode
  useEffect(() => {
    if (inferenceMode === 'comfyui') {
      fetch('/api/studio/comfyui/object_info')
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (data && data.KSampler && data.KSampler.input && data.KSampler.input.required) {
            const samplers = data.KSampler.input.required.sampler_name?.[0];
            if (Array.isArray(samplers)) setComfySamplers(samplers);
            const schedulers = data.KSampler.input.required.scheduler?.[0];
            if (Array.isArray(schedulers)) setComfySchedulers(schedulers);
          }
          if (data && data.ControlNetLoader && data.ControlNetLoader.input && data.ControlNetLoader.input.required) {
            const cnets = data.ControlNetLoader.input.required.control_net_name?.[0];
            if (Array.isArray(cnets)) setComfyControlNets(cnets);
          }
        })
        .catch(err => console.error("Error fetching ComfyUI object info:", err));
    }
  }, [inferenceMode]);

  // Filter models based on selected inference mode
  const filteredModels = models.filter(m => 
    inferenceMode === 'diffusers' ? m.provider === 'local' : m.provider === 'comfyui'
  );

  // Reset selected model when active list changes
  useEffect(() => {
    if (filteredModels.length > 0) {
      setSelectedModel(filteredModels[0].name);
    } else {
      setSelectedModel('');
    }
  }, [inferenceMode, models]);

  // Image Generation Handler
  const generateWithTemplateControlNet = async () => {
    setIsGenerating(true);
    try {
      let controlnetImageB64: string | null = null;
      if (controlNetEnabled) {
        if (controlNetSource === 'template') {
          controlnetImageB64 = await captureTemplateForControlNet();
        } else {
          controlnetImageB64 = customControlNetImage;
        }
        if (!controlnetImageB64) {
          alert("Please upload a custom ControlNet guidance image first!");
          setIsGenerating(false);
          return;
        }
      }

      const [widthStr, heightStr] = resolution.split('x');
      const payload: any = {
        prompt,
        negative_prompt: negativePrompt,
        width: parseInt(widthStr),
        height: parseInt(heightStr),
        steps,
        cfg_scale: cfgScale,
        sampler_name: sampler,
        scheduler,
        seed: seed.trim() !== '' ? parseInt(seed) : null,
        provider: inferenceMode,
        model: selectedModel || null
      };

      if (controlNetEnabled) {
        payload.controlnet_type = controlNetType;
        payload.controlnet_image = controlnetImageB64;
        payload.controlnet_strength = controlNetStrength;
      }

      const response = await fetch('/api/studio/generate-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Image generation failed.");
      }

      const data = await response.json();
      if (data && data.image_base64) {
        setGeneratedImg(`data:image/png;base64,${data.image_base64}`);
        // Trigger sync to gallery if asset ID is returned
        if (data.asset && data.asset.id && onImageGenerated) {
          onImageGenerated(data.asset.id);
        }
      } else {
        throw new Error("No image data returned from backend.");
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred during generation');
    } finally {
      setIsGenerating(false);
    }
  };

  const handlePreviewControlNet = async () => {
    let baseImg = customControlNetImage;
    if (controlNetSource === 'template' && activeSlotId) {
      const slot = slots.find(s => s.id === activeSlotId);
      if (slot) {
        const slotEl = document.getElementById(`slot-preview-${slot.id}`);
        if (slotEl) {
          const canvas = await html2canvas(slotEl as HTMLElement, { useCORS: true, backgroundColor: null });
          baseImg = canvas.toDataURL('image/png');
        }
      }
    }
    
    if (!baseImg) {
      setError("No source image available for ControlNet preprocessing.");
      return;
    }
    
    setIsPreprocessing(true);
    setError(null);
    try {
      const res = await fetch('/api/studio/preprocess-controlnet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_base64: baseImg,
          preprocessor: controlNetType
        })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Preprocessing failed');
      }
      const data = await res.json();
      setControlNetPreviewMap(`data:image/png;base64,${data.image_base64}`);
    } catch (err: any) {
      setError(err.message || 'An error occurred during preprocessing');
    } finally {
      setIsPreprocessing(false);
    }
  };

  // Background Remover Handler
  const handleRemoveBackground = async () => {
    if (!generatedImg) return;
    setIsRemovingBg(true);
    try {
      const response = await fetch('/api/studio/remove-background', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_base64: generatedImg })
      });
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Background removal failed.");
      }
      const data = await response.json();
      if (data && data.image_base64) {
        setGeneratedImg(data.image_base64);
      } else {
        throw new Error("No transparent image data returned from backend.");
      }
    } catch (err: any) {
      console.error(err);
      alert(`Background removal failed: ${err.message}`);
    } finally {
      setIsRemovingBg(false);
    }
  };

  const getCroppedImageBase64 = (): string | null => {
    if (!imgRef.current || !crop || crop.width === 0 || crop.height === 0) return null;

    const canvas = document.createElement('canvas');
    const scaleX = imgRef.current.naturalWidth / imgRef.current.width;
    const scaleY = imgRef.current.naturalHeight / imgRef.current.height;

    canvas.width = crop.width * scaleX;
    canvas.height = crop.height * scaleY;
    const ctx = canvas.getContext('2d');

    if (!ctx) return null;

    ctx.drawImage(
      imgRef.current,
      crop.x * scaleX,
      crop.y * scaleY,
      crop.width * scaleX,
      crop.height * scaleY,
      0,
      0,
      crop.width * scaleX,
      crop.height * scaleY
    );

    return canvas.toDataURL('image/png'); // Save as PNG to support transparency!
  };

  const handleAssign = (slotId: string) => {
    if (slots.length === 0) {
      alert("No asset slots available to assign to!");
      return;
    }
    const croppedB64 = getCroppedImageBase64();
    if (croppedB64) {
      onAssignSlot(slotId, croppedB64);
    } else {
      alert("Please select an area to crop first!");
    }
  };

  const handleAspectChange = useCallback((newAspect: number | undefined) => {
    setAspect(newAspect);
    if (imgRef.current && newAspect) {
      const { width, height } = imgRef.current;
      const centered = centerCrop(
        makeAspectCrop(
          { unit: '%', width: 80 },
          newAspect,
          width,
          height
        ),
        width,
        height
      );
      setCrop(centered);
    } else {
      setCrop(undefined);
    }
  }, []);

  const currentSlot = slots.find(s => s.id === activeSlotId);
  const slotAspect = currentSlot?.aspect;

  useEffect(() => {
    const exists = slots.some(s => s.id === selectedSlotId);
    if (!exists && slots.length > 0) {
      onSlotSelect?.(slots[0].id);
    }
  }, [slots, selectedSlotId, onSlotSelect]);

  useEffect(() => {
    const currentSlot = slots.find(s => s.id === selectedSlotId);
    if (currentSlot) {
      handleAspectChange(currentSlot.aspect);
    }
  }, [selectedSlotId, handleAspectChange]);

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const { width, height } = e.currentTarget;
    if (aspect) {
      const centered = centerCrop(
        makeAspectCrop(
          { unit: '%', width: 80 },
          aspect,
          width,
          height
        ),
        width,
        height
      );
      setCrop(centered);
    }
  };

  // Helper to handle custom ControlNet image files
  const handleCustomImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onloadend = () => {
      setCustomControlNetImage(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', height: '100%', fontFamily: 'Outfit, sans-serif', color: 'var(--text-main)', overflowY: 'auto', paddingRight: '0.25rem' }}>
      {/* SDXL Prompt Inputs & Engine Settings */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', padding: '1rem', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px' }}>
        
        {/* Inference Mode Toggle */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Inference Provider</label>
          <div style={{ display: 'flex', gap: '0.5rem', background: 'var(--bg-main)', padding: '0.2rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
            <button
              onClick={() => setInferenceMode('diffusers')}
              style={{
                flex: 1,
                padding: '0.4rem',
                border: 'none',
                borderRadius: '4px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                background: inferenceMode === 'diffusers' ? 'var(--accent)' : 'transparent',
                color: inferenceMode === 'diffusers' ? 'white' : 'var(--text-secondary)',
                transition: 'all 0.2s'
              }}
            >
              Internal (Diffusers)
            </button>
            <button
              onClick={() => setInferenceMode('comfyui')}
              style={{
                flex: 1,
                padding: '0.4rem',
                border: 'none',
                borderRadius: '4px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                background: inferenceMode === 'comfyui' ? 'var(--accent)' : 'transparent',
                color: inferenceMode === 'comfyui' ? 'white' : 'var(--text-secondary)',
                transition: 'all 0.2s'
              }}
            >
              ComfyUI
            </button>
          </div>
        </div>

        {/* Model Dropdown */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>SDXL Model Checkpoint</label>
          {filteredModels.length > 0 ? (
            <select
              value={selectedModel}
              onChange={e => setSelectedModel(e.target.value)}
              style={{
                padding: '0.5rem 0.7rem',
                background: 'var(--bg-main)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                color: 'var(--text-main)',
                outline: 'none',
                fontSize: '0.85rem',
                fontFamily: 'inherit',
                cursor: 'pointer'
              }}
            >
              {filteredModels.map(m => (
                <option key={m.name} value={m.name}>{m.name}</option>
              ))}
            </select>
          ) : (
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', padding: '0.5rem', background: 'var(--bg-main)', borderRadius: '6px', border: '1px dashed var(--border-color)' }}>
              No models found for {inferenceMode === 'diffusers' ? 'Local folder' : 'ComfyUI'}.
            </div>
          )}
        </div>

        {/* Prompts */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>SDXL Prompt</label>
          <textarea 
            value={prompt} 
            onChange={e => setPrompt(e.target.value)} 
            rows={2}
            style={{ 
              padding: '0.5rem 0.7rem', 
              background: 'var(--bg-main)', 
              border: '1px solid var(--border-color)', 
              borderRadius: '6px', 
              color: 'var(--text-main)', 
              outline: 'none', 
              fontSize: '0.85rem',
              resize: 'vertical',
              fontFamily: 'inherit'
            }}
          />
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Negative Prompt</label>
          <input 
            type="text"
            value={negativePrompt} 
            onChange={e => setNegativePrompt(e.target.value)} 
            style={{ 
              padding: '0.5rem 0.7rem', 
              background: 'var(--bg-main)', 
              border: '1px solid var(--border-color)', 
              borderRadius: '6px', 
              color: 'var(--text-main)', 
              outline: 'none', 
              fontSize: '0.85rem',
              fontFamily: 'inherit'
            }}
          />
        </div>

        {/* Collapsible Advanced parameters */}
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '0.5rem' }}>
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--accent)',
              fontSize: '0.75rem',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
              padding: 0
            }}
          >
            {showAdvanced ? '▼ Hide Advanced Settings' : '▶ Show Advanced Settings'}
          </button>
          {showAdvanced && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', marginTop: '0.6rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Resolution</label>
                  <select
                    value={resolution}
                    onChange={e => setResolution(e.target.value)}
                    style={{ padding: '0.4rem', background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: '4px', color: '#fff', fontSize: '0.75rem' }}
                  >
                    <option value="1024x1024">1024x1024 (Square)</option>
                    <option value="768x1024">768x1024 (Portrait)</option>
                    <option value="1024x768">1024x768 (Landscape)</option>
                  </select>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Inference Steps ({steps})</label>
                  <input
                    type="range" min="10" max="60" value={steps}
                    onChange={e => setSteps(parseInt(e.target.value))}
                    style={{ accentColor: 'var(--accent)' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>CFG Scale ({cfgScale.toFixed(1)})</label>
                  <input
                    type="range" min="1.0" max="15.0" step="0.5" value={cfgScale}
                    onChange={e => setCfgScale(parseFloat(e.target.value))}
                    style={{ accentColor: 'var(--accent)' }}
                  />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Seed (optional)</label>
                  <input
                    type="text" placeholder="Random" value={seed}
                    onChange={e => setSeed(e.target.value)}
                    style={{ padding: '0.4rem', background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: '4px', color: '#fff', fontSize: '0.75rem', outline: 'none' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Sampler</label>
                  <select
                    value={sampler}
                    onChange={e => setSampler(e.target.value)}
                    style={{ padding: '0.4rem', background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: '4px', color: '#fff', fontSize: '0.75rem' }}
                  >
                    {inferenceMode === 'comfyui' ? comfySamplers.map(s => (
                      <option key={s} value={s}>{s}</option>
                    )) : comfySamplers.slice(0,4).map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Scheduler</label>
                  <select
                    value={scheduler}
                    onChange={e => setScheduler(e.target.value)}
                    style={{ padding: '0.4rem', background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: '4px', color: '#fff', fontSize: '0.75rem' }}
                  >
                    {inferenceMode === 'comfyui' ? comfySchedulers.map(s => (
                      <option key={s} value={s}>{s}</option>
                    )) : comfySchedulers.slice(0,4).map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Collapsible ControlNet settings */}
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '0.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)' }}>ControlNet Integration</span>
            <input
              type="checkbox"
              checked={controlNetEnabled}
              onChange={e => setControlNetEnabled(e.target.checked)}
              style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
            />
          </div>
          
          {controlNetEnabled && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', marginTop: '0.6rem', padding: '0.8rem', backgroundColor: 'rgba(0,0,0,0.15)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.02)' }}>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Model / Type</label>
                  <select
                    value={controlNetType}
                    onChange={e => setControlNetType(e.target.value)}
                    style={{ padding: '0.5rem', background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: '4px', color: '#fff' }}
                  >
                    {comfyControlNets.map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Strength ({controlNetStrength})</label>
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.05"
                    value={controlNetStrength}
                    onChange={e => setControlNetStrength(parseFloat(e.target.value))}
                    style={{ marginTop: '0.5rem', accentColor: 'var(--accent)' }}
                  />
                </div>
              </div>

              <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <button 
                  onClick={handlePreviewControlNet}
                  disabled={isPreprocessing}
                  style={{
                    background: 'rgba(255,255,255,0.1)',
                    border: '1px solid var(--border-color)',
                    color: '#fff',
                    padding: '0.4rem',
                    borderRadius: '4px',
                    cursor: isPreprocessing ? 'not-allowed' : 'pointer',
                    fontSize: '0.75rem'
                  }}
                >
                  {isPreprocessing ? 'Preprocessing...' : 'Preview ControlNet Map'}
                </button>
                {controlNetPreviewMap && (
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: '4px', overflow: 'hidden', maxHeight: '200px', display: 'flex', justifyContent: 'center', background: '#000' }}>
                    <img src={controlNetPreviewMap} alt="ControlNet Preview" style={{ maxWidth: '100%', maxHeight: '200px', objectFit: 'contain' }} />
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Guidance Image Source</label>
                <div style={{ display: 'flex', gap: '0.4rem' }}>
                  <button
                    onClick={() => setControlNetSource('template')}
                    style={{
                      flex: 1,
                      padding: '0.3rem',
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      borderRadius: '4px',
                      border: '1px solid var(--border-color)',
                      background: controlNetSource === 'template' ? 'var(--accent)' : 'var(--bg-main)',
                      color: 'white'
                    }}
                  >
                    Template Capture
                  </button>
                  <button
                    onClick={() => setControlNetSource('custom')}
                    style={{
                      flex: 1,
                      padding: '0.3rem',
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      borderRadius: '4px',
                      border: '1px solid var(--border-color)',
                      background: controlNetSource === 'custom' ? 'var(--accent)' : 'var(--bg-main)',
                      color: 'white'
                    }}
                  >
                    Upload Custom
                  </button>
                </div>
              </div>

              {controlNetSource === 'custom' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Custom Guidance Image</label>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleCustomImageUpload}
                      style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}
                    />
                    {customControlNetImage && (
                      <img
                        src={customControlNetImage}
                        alt="Guidance preview"
                        style={{ width: '40px', height: '40px', objectFit: 'cover', borderRadius: '4px', border: '1px solid var(--border-color)' }}
                      />
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Generate Button */}
        <button 
          onClick={generateWithTemplateControlNet} 
          disabled={isGenerating}
          style={{ 
            padding: '0.6rem 1.2rem', 
            cursor: 'pointer', 
            background: 'linear-gradient(135deg, var(--accent), #5a4bcf)', 
            color: 'white', 
            border: 'none', 
            borderRadius: '6px',
            fontWeight: 600,
            fontSize: '0.85rem',
            marginTop: '0.25rem',
            boxShadow: '0 4px 12px var(--accent-glow)',
            transition: 'all 0.2s'
          }}
        >
          {isGenerating ? 'Generating Image...' : 'Generate Image'}
        </button>
      </div>

      {/* Image Preview / Crop Area */}
      <div style={{ flex: 1, minHeight: '320px', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>SDXL Output Canvas</span>
          {generatedImg && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              
              {/* Background Remover Action Button */}
              <button
                onClick={handleRemoveBackground}
                disabled={isRemovingBg}
                style={{
                  padding: '0.25rem 0.6rem',
                  fontSize: '0.75rem',
                  background: 'linear-gradient(135deg, #ff007f, #b5005b)',
                  border: 'none',
                  color: 'white',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontWeight: 600,
                  boxShadow: '0 2px 6px rgba(255, 0, 127, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                  transition: 'all 0.2s'
                }}
              >
                {isRemovingBg ? 'Removing Bg...' : '✨ Remove Background'}
              </button>
              
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginLeft: '0.5rem' }}>Crop Ratio:</span>
              {aspect !== slotAspect && (
                <button 
                  onClick={() => handleAspectChange(slotAspect)} 
                  style={{ 
                    padding: '0.25rem 0.5rem', 
                    fontSize: '0.75rem', 
                    background: 'var(--bg-secondary)', 
                    border: '1px solid var(--accent)', 
                    color: 'var(--accent)', 
                    borderRadius: '4px', 
                    cursor: 'pointer',
                    fontWeight: 600
                  }}
                >
                  Reset to Slot
                </button>
              )}
              <button 
                onClick={() => handleAspectChange(1)} 
                style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', background: aspect === 1 ? 'var(--accent)' : 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: aspect === 1 ? 'white' : 'var(--text-main)', borderRadius: '4px', cursor: 'pointer' }}
              >
                1:1 (Face)
              </button>
              <button 
                onClick={() => handleAspectChange(3/4)} 
                style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', background: aspect === 3/4 ? 'var(--accent)' : 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: aspect === 3/4 ? 'white' : 'var(--text-main)', borderRadius: '4px', cursor: 'pointer' }}
              >
                3:4 (Body)
              </button>
              <button 
                onClick={() => handleAspectChange(undefined)} 
                style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', background: aspect === undefined ? 'var(--accent)' : 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: aspect === undefined ? 'white' : 'var(--text-main)', borderRadius: '4px', cursor: 'pointer' }}
              >
                Free
              </button>
            </div>
          )}
        </div>

        {generatedImg ? (
          <div style={{ flex: 1, overflow: 'auto', border: '1px solid var(--border-color)', borderRadius: '8px', backgroundColor: 'rgba(0,0,0,0.15)', display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '1rem', position: 'relative' }}>
            <ReactCrop crop={crop} aspect={aspect} onChange={c => setCrop(c)}>
              <img 
                ref={imgRef}
                src={generatedImg} 
                alt="Generated" 
                style={{ maxWidth: '100%', maxHeight: '420px', objectFit: 'contain', borderRadius: '4px' }}
                crossOrigin="anonymous"
                onLoad={handleImageLoad}
              />
            </ReactCrop>
          </div>
        ) : (
          <div style={{ flex: 1, border: '2px dashed var(--border-color)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', borderRadius: '8px', gap: '0.5rem', background: 'rgba(255,255,255,0.01)', minHeight: '300px' }}>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: 0 }}>Generated image will appear here.</p>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', margin: 0 }}>Template layout details are captured and used as style templates.</p>
          </div>
        )}
      </div>
      
      {/* Assignment Bar */}
      {generatedImg && (
        <div style={{ padding: '1rem', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <strong style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Assign Crop To:</strong>
          <select 
            value={selectedSlotId} 
            onChange={e => {
              const val = e.target.value;
              if (onSlotSelect) {
                onSlotSelect(val);
              }
              const s = slots.find(x => x.id === val);
              if (s) setAspect(s.aspect);
            }} 
            style={{
              padding: '0.4rem 0.8rem',
              background: 'var(--bg-main)',
              border: '1px solid var(--border-color)',
              borderRadius: '6px',
              color: 'var(--text-main)',
              outline: 'none',
              fontSize: '0.85rem',
              fontFamily: 'inherit',
              cursor: 'pointer',
              minWidth: '150px'
            }}
          >
            {slots.map(slot => (
              <option key={slot.id} value={slot.id} style={{ background: 'var(--bg-main)', color: 'var(--text-main)' }}>
                {slot.label}
              </option>
            ))}
          </select>
          <button 
            onClick={() => handleAssign(selectedSlotId)} 
            style={{ 
              padding: '0.4rem 1rem', 
              background: 'linear-gradient(135deg, var(--accent), #5a4bcf)', 
              color: 'white', 
              border: 'none', 
              borderRadius: '6px', 
              fontSize: '0.85rem', 
              fontWeight: 600, 
              cursor: 'pointer',
              boxShadow: '0 2px 8px var(--accent-glow)',
              transition: 'all 0.2s'
            }}
            onMouseEnter={e => {
              e.currentTarget.style.filter = 'brightness(1.1)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.filter = 'none';
            }}
          >
            Assign to Slot
          </button>
        </div>
      )}
    </div>
  );
}
