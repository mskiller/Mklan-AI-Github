"use client";

import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

interface NodeData {
  label: string;
}

interface VisualWorkflowGraphProps {
  workflow: {
    nodes: any[];
    edges: any[];
  } | null;
}

export function VisualWorkflowGraph({ workflow }: VisualWorkflowGraphProps) {
  const nodes = useMemo(() => {
    if (!workflow?.nodes) return [];
    return workflow.nodes.map((n: any) => ({
      ...n,
      data: { label: n.label },
      // React Flow expectations:
      id: String(n.id),
      position: n.position || { x: 0, y: 0 },
      style: {
        background: "var(--panel-bg)",
        color: "var(--text)",
        border: "1px solid var(--border)",
        borderRadius: "8px",
        padding: "10px",
        fontSize: "12px",
        width: n.width || 150,
      }
    }));
  }, [workflow]);

  const edges = useMemo(() => {
    if (!workflow?.edges) return [];
    return workflow.edges.map((e: any) => ({
      ...e,
      id: String(e.id),
      source: String(e.source),
      target: String(e.target),
      animated: true,
      style: { stroke: "var(--accent)" }
    }));
  }, [workflow]);

  if (!workflow || nodes.length === 0) {
    return (
      <div className="empty-workflow stack center">
        <p className="subdued">No visual workflow extracted yet.</p>
        <p className="subdued small">Use the "Extract Visual Workflow" button to analyze this image.</p>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: "500px", background: "var(--app-bg)", borderRadius: "12px", border: "1px solid var(--border)" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        colorMode="dark"
      >
        <Background gap={12} size={1} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
