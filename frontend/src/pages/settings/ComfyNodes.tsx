import { useState, useRef } from "react";
import {
  Layers,
  Trash2,
  Plus,
  Settings2,
  Code,
  Check,
  Copy
} from "lucide-react";

interface Node {
  id: string;
  type: string;
  title: string;
  x: number;
  y: number;
  inputs: { [key: string]: { type: string; value: string; linkedTo?: string } };
  outputs: { [key: string]: { type: string } };
  properties: { [key: string]: string | number | boolean };
}

export function ComfyNodes() {
  const [nodes, setNodes] = useState<Node[]>([
    {
      id: "1",
      type: "LoadCheckpoint",
      title: "Load Checkpoint",
      x: 50,
      y: 100,
      inputs: {},
      outputs: {
        MODEL: { type: "MODEL" },
        CLIP: { type: "CLIP" },
        VAE: { type: "VAE" }
      },
      properties: {
        ckpt_name: "example-checkpoint.safetensors"
      }
    },
    {
      id: "2",
      type: "ClipTextEncode",
      title: "CLIP Text Encode (Positive)",
      x: 320,
      y: 50,
      inputs: {
        clip: { type: "CLIP", value: "1.CLIP" }
      },
      outputs: {
        CONDITIONING: { type: "CONDITIONING" }
      },
      properties: {
        text: "cinematic film style, cyberpunk scene, ultra-realistic, highly detailed, 8k"
      }
    },
    {
      id: "3",
      type: "ClipTextEncode",
      title: "CLIP Text Encode (Negative)",
      x: 320,
      y: 240,
      inputs: {
        clip: { type: "CLIP", value: "1.CLIP" }
      },
      outputs: {
        CONDITIONING: { type: "CONDITIONING" }
      },
      properties: {
        text: "blurry, low quality, worst quality, deformed, bad anatomy, text, watermark"
      }
    },
    {
      id: "4",
      type: "KSampler",
      title: "KSampler",
      x: 600,
      y: 120,
      inputs: {
        model: { type: "MODEL", value: "1.MODEL" },
        positive: { type: "CONDITIONING", value: "2.CONDITIONING" },
        negative: { type: "CONDITIONING", value: "3.CONDITIONING" },
        latent_image: { type: "LATENT", value: "5.LATENT" }
      },
      outputs: {
        LATENT: { type: "LATENT" }
      },
      properties: {
        seed: 42,
        steps: 25,
        cfg: 7.0,
        sampler_name: "euler",
        scheduler: "normal",
        denoise: 1.0
      }
    },
    {
      id: "5",
      type: "EmptyLatentImage",
      title: "Empty Latent Image",
      x: 320,
      y: 430,
      inputs: {},
      outputs: {
        LATENT: { type: "LATENT" }
      },
      properties: {
        width: 1024,
        height: 1024,
        batch_size: 1
      }
    },
    {
      id: "6",
      type: "VAEDecode",
      title: "VAE Decode",
      x: 880,
      y: 150,
      inputs: {
        samples: { type: "LATENT", value: "4.LATENT" },
        vae: { type: "VAE", value: "1.VAE" }
      },
      outputs: {
        IMAGE: { type: "IMAGE" }
      },
      properties: {}
    }
  ]);

  const [selectedNodeId, setSelectedNodeId] = useState<string>("4");
  const [copied, setCopied] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const dragInfo = useRef<{ nodeId: string; startX: number; startY: number } | null>(null);

  // Generate equivalent ComfyUI JSON schema in real time
  const generateComfyJson = () => {
    const output: { [key: string]: any } = {};
    nodes.forEach(node => {
      const class_type = node.type;
      const inputs: { [key: string]: any } = {};

      // Fill hardcoded values and links
      Object.entries(node.properties).forEach(([k, v]) => {
        inputs[k] = v;
      });

      Object.entries(node.inputs).forEach(([k, config]) => {
        if (config.value) {
          const parts = config.value.split(".");
          inputs[k] = [parts[0], Number(parts[0]) === 1 ? (parts[1] === "MODEL" ? 0 : parts[1] === "CLIP" ? 1 : 2) : 0];
        }
      });

      output[node.id] = {
        inputs,
        class_type
      };
    });
    return JSON.stringify(output, null, 2);
  };

  const handleMouseDown = (nodeId: string, event: React.MouseEvent) => {
    if ((event.target as HTMLElement).tagName === "INPUT" || (event.target as HTMLElement).tagName === "TEXTAREA" || (event.target as HTMLElement).tagName === "SELECT") {
      return;
    }
    setSelectedNodeId(nodeId);
    dragInfo.current = {
      nodeId,
      startX: event.clientX - nodes.find(n => n.id === nodeId)!.x,
      startY: event.clientY - nodes.find(n => n.id === nodeId)!.y
    };
  };

  const handleMouseMove = (event: React.MouseEvent) => {
    if (!dragInfo.current) return;
    const { nodeId, startX, startY } = dragInfo.current;
    
    let nextX = event.clientX - startX;
    let nextY = event.clientY - startY;

    if (nextX < 0) nextX = 0;
    if (nextY < 0) nextY = 0;
    if (nextX > 1150) nextX = 1150;
    if (nextY > 580) nextY = 580;

    setNodes(prev =>
      prev.map(n => (n.id === nodeId ? { ...n, x: nextX, y: nextY } : n))
    );
  };

  const handleMouseUp = () => {
    dragInfo.current = null;
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(generateComfyJson());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const selectedNode = nodes.find(n => n.id === selectedNodeId);

  const handlePropChange = (nodeId: string, propKey: string, value: string | number | boolean) => {
    setNodes(prev =>
      prev.map(n => {
        if (n.id !== nodeId) return n;
        return {
          ...n,
          properties: {
            ...n.properties,
            [propKey]: value
          }
        };
      })
    );
  };

  const addCustomNode = (type: string) => {
    const nextId = (Math.max(...nodes.map(n => Number(n.id))) + 1).toString();
    const newNode: Node = {
      id: nextId,
      type,
      title: type.replace(/([A-Z])/g, " $1").trim(),
      x: 100 + Math.random() * 100,
      y: 150 + Math.random() * 100,
      inputs: type === "KSampler" ? {
        model: { type: "MODEL", value: "1.MODEL" },
        positive: { type: "CONDITIONING", value: "2.CONDITIONING" },
        negative: { type: "CONDITIONING", value: "3.CONDITIONING" },
        latent_image: { type: "LATENT", value: "5.LATENT" }
      } : {},
      outputs: type === "KSampler" ? { LATENT: { type: "LATENT" } } : { OUTPUT: { type: "IMAGE" } },
      properties: type === "KSampler" ? {
        seed: Math.floor(Math.random() * 1000000),
        steps: 20,
        cfg: 8.0,
        sampler_name: "euler",
        scheduler: "normal",
        denoise: 1.0
      } : { text: "new node prompt" }
    };

    setNodes(prev => [...prev, newNode]);
    setSelectedNodeId(nextId);
  };

  const deleteNode = (id: string) => {
    if (nodes.length <= 1) return;
    setNodes(prev => prev.filter(n => n.id !== id));
    setSelectedNodeId(nodes.filter(n => n.id !== id)[0].id);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: "2rem", height: "100%", minHeight: "680px" }}>
      {/* Visual Canvas Panel */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h3 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0, color: "#fff", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Layers size={18} color="var(--accent)" />
              ComfyUI Interactive Node Graph
            </h3>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Drag nodes to rearrange them. Connected wires dynamically track node handles.
            </span>
          </div>

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              onClick={() => addCustomNode("KSampler")}
              className="ghost-button"
              style={{ padding: "0.4rem 0.8rem", fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
            >
              <Plus size={12} /> KSampler Node
            </button>
            <button
              onClick={() => addCustomNode("ClipTextEncode")}
              className="ghost-button"
              style={{ padding: "0.4rem 0.8rem", fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
            >
              <Plus size={12} /> Text Encode Node
            </button>
          </div>
        </div>

        {/* The Node Canvas Area */}
        <div
          ref={canvasRef}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          style={{
            position: "relative",
            width: "100%",
            height: "600px",
            background: "rgba(0,0,0,0.35)",
            backgroundImage: "radial-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 0)",
            backgroundSize: "24px 24px",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-lg)",
            overflow: "hidden"
          }}
        >
          {/* SVG Connection Lines */}
          <svg style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 1 }}>
            <defs>
              <linearGradient id="wire-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#7c6aff" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#c084fc" stopOpacity="0.8" />
              </linearGradient>
            </defs>

            {nodes.map(node =>
              Object.entries(node.inputs).map(([inputKey, config]) => {
                if (!config.value) return null;
                const [targetNodeId, targetPort] = config.value.split(".");
                const sourceNode = nodes.find(n => n.id === targetNodeId);
                if (!sourceNode) return null;

                const x1 = sourceNode.x + 220;
                const y1 = sourceNode.y + 40 + Object.keys(sourceNode.outputs).indexOf(targetPort) * 20;
                
                const x2 = node.x;
                const y2 = node.y + 40 + Object.keys(node.inputs).indexOf(inputKey) * 20;

                const controlX = x1 + Math.abs(x2 - x1) * 0.4;
                const pathStr = `M ${x1} ${y1} C ${controlX} ${y1}, ${x2 - Math.abs(x2 - x1) * 0.4} ${y2}, ${x2} ${y2}`;

                return (
                  <g key={`${node.id}-${inputKey}`}>
                    <path
                      d={pathStr}
                      fill="none"
                      stroke="rgba(0,0,0,0.4)"
                      strokeWidth="5"
                    />
                    <path
                      d={pathStr}
                      fill="none"
                      stroke="url(#wire-gradient)"
                      strokeWidth="2.5"
                      style={{ filter: "drop-shadow(0 2px 4px rgba(124, 106, 255, 0.3))" }}
                    />
                    <circle cx={x1} cy={y1} r="4" fill="#c084fc" />
                    <circle cx={x2} cy={y2} r="4" fill="#7c6aff" />
                  </g>
                );
              })
            )}
          </svg>

          {/* Floating Nodes Cards */}
          {nodes.map(node => {
            const isSelected = node.id === selectedNodeId;
            return (
              <div
                key={node.id}
                onMouseDown={(e) => handleMouseDown(node.id, e)}
                style={{
                  position: "absolute",
                  left: `${node.x}px`,
                  top: `${node.y}px`,
                  width: "220px",
                  background: isSelected ? "rgba(22, 20, 28, 0.9)" : "rgba(12, 10, 16, 0.8)",
                  backdropFilter: "blur(12px)",
                  border: isSelected ? "2px solid var(--accent)" : "1px solid var(--border-color)",
                  borderRadius: "10px",
                  boxShadow: isSelected ? "0 8px 32px rgba(124,106,255,0.25)" : "0 4px 20px rgba(0,0,0,0.3)",
                  zIndex: isSelected ? 10 : 5,
                  cursor: "grab",
                  userSelect: "none"
                }}
              >
                {/* Node Title Header */}
                <div
                  style={{
                    padding: "0.6rem 0.8rem",
                    borderBottom: "1px solid var(--border-color)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    background: isSelected ? "rgba(124, 106, 255, 0.1)" : "rgba(255, 255, 255, 0.02)",
                    borderTopLeftRadius: "8px",
                    borderTopRightRadius: "8px"
                  }}
                >
                  <span style={{ fontWeight: 700, fontSize: "0.8rem", color: isSelected ? "#fff" : "var(--text-secondary)" }}>
                    {node.title}
                  </span>
                  <div style={{ display: "flex", gap: "0.3rem" }}>
                    <span style={{ fontSize: "0.65rem", padding: "0.1rem 0.3rem", background: "rgba(255,255,255,0.06)", borderRadius: "4px", color: "var(--text-muted)" }}>
                      #{node.id}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteNode(node.id);
                      }}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "rgba(255,255,255,0.2)", padding: 0 }}
                      onMouseEnter={(e) => e.currentTarget.style.color = "#ff7878"}
                      onMouseLeave={(e) => e.currentTarget.style.color = "rgba(255,255,255,0.2)"}
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>

                {/* Ports layout */}
                <div style={{ padding: "0.8rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  {/* Inputs ports */}
                  {Object.keys(node.inputs).length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                      {Object.entries(node.inputs).map(([key, config]) => (
                        <div key={key} style={{ display: "flex", alignItems: "center", fontSize: "0.7rem", color: "var(--text-secondary)", gap: "0.3rem" }}>
                          <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#7c6aff" }} />
                          <span>{key} ({config.type})</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Outputs ports */}
                  {Object.keys(node.outputs).length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem", alignItems: "flex-end", marginTop: Object.keys(node.inputs).length > 0 ? "0.5rem" : 0 }}>
                      {Object.entries(node.outputs).map(([key, config]) => (
                        <div key={key} style={{ display: "flex", alignItems: "center", fontSize: "0.7rem", color: "var(--text-secondary)", gap: "0.3rem" }}>
                          <span>{key} ({config.type})</span>
                          <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#c084fc" }} />
                        </div>
                      ))}
                    </div>
                  )}

                  {node.properties.ckpt_name && (
                    <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginTop: "0.4rem", wordBreak: "break-all", background: "rgba(0,0,0,0.2)", padding: "0.3rem", borderRadius: "4px" }}>
                      <strong>CKPT:</strong> {node.properties.ckpt_name}
                    </div>
                  )}
                  {node.properties.text && (
                    <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginTop: "0.4rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", background: "rgba(0,0,0,0.2)", padding: "0.3rem", borderRadius: "4px" }}>
                      <strong>PROMPT:</strong> {node.properties.text as string}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Side Controller Panel & JSON Exporter */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        {/* Node Properties Form */}
        <div className="glass-panel" style={{ padding: "1.5rem", background: "rgba(255,255,255,0.015)", border: "1px solid var(--border-color)", borderRadius: "var(--radius-lg)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.6rem", marginBottom: "1rem" }}>
            <Settings2 size={16} color="var(--accent)" />
            <h4 style={{ fontSize: "0.95rem", fontWeight: 700, color: "#fff", margin: 0 }}>
              {selectedNode ? `${selectedNode.title} Parameters` : "Node Inspector"}
            </h4>
          </div>

          {selectedNode ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {Object.keys(selectedNode.properties).length === 0 ? (
                <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>
                  This node does not have any adjustable parameters.
                </p>
              ) : (
                Object.entries(selectedNode.properties).map(([key, val]) => (
                  <label key={key} style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                    <span style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "var(--text-secondary)", fontWeight: 600 }}>
                      {key.replace(/_/g, " ")}
                    </span>
                    {typeof val === "number" ? (
                      <input
                        type="number"
                        value={val}
                        onChange={(e) => handlePropChange(selectedNode.id, key, Number(e.target.value))}
                        style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem" }}
                      />
                    ) : typeof val === "boolean" ? (
                      <input
                        type="checkbox"
                        checked={val}
                        onChange={(e) => handlePropChange(selectedNode.id, key, e.target.checked)}
                      />
                    ) : (
                      <textarea
                        value={val}
                        onChange={(e) => handlePropChange(selectedNode.id, key, e.target.value)}
                        style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem", minHeight: key === "text" ? "120px" : "40px" }}
                      />
                    )}
                  </label>
                ))
              )}
            </div>
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>
              Select a node in the graph to configure its parameters.
            </p>
          )}
        </div>

        {/* Real-time JSON schema block */}
        <div className="glass-panel" style={{ padding: "1.5rem", background: "rgba(0,0,0,0.2)", border: "1px solid var(--border-color)", borderRadius: "var(--radius-lg)", display: "flex", flexDirection: "column", gap: "0.8rem", flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.6rem" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#fff", display: "flex", alignItems: "center", gap: "0.3rem" }}>
              <Code size={14} color="var(--accent)" />
              ComfyUI JSON API Output
            </span>
            <button
              onClick={handleCopy}
              className="ghost-button"
              style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
            >
              {copied ? <Check size={12} color="#6be698" /> : <Copy size={12} />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>

          <pre style={{
            fontSize: "0.75rem",
            color: "rgba(255,255,255,0.7)",
            background: "rgba(0,0,0,0.3)",
            padding: "0.8rem",
            borderRadius: "6px",
            border: "1px solid rgba(255,255,255,0.04)",
            fontFamily: "monospace",
            overflowX: "auto",
            maxHeight: "300px",
            margin: 0,
            lineHeight: "1.4"
          }}>
            <code>{generateComfyJson()}</code>
          </pre>
        </div>
      </div>
    </div>
  );
}
