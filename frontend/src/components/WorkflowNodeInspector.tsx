import { useMemo, useState } from 'react';
import { Braces, GitBranch, Network } from 'lucide-react';

export interface WorkflowSummaryNode {
  id: string;
  class_type: string;
  inputs: string[];
}

export interface WorkflowSummaryEdge {
  from: string;
  to: string;
  input: string;
  output: number | string;
}

export interface WorkflowSummary {
  node_count?: number;
  class_counts?: Record<string, number>;
  placeholders?: string[];
  nodes?: WorkflowSummaryNode[];
  edges?: WorkflowSummaryEdge[];
}

export function WorkflowNodeInspector({ summary }: { summary?: WorkflowSummary | null }) {
  const nodes = summary?.nodes || [];
  const edges = summary?.edges || [];
  const classEntries = Object.entries(summary?.class_counts || {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const [selectedNodeId, setSelectedNodeId] = useState(nodes[0]?.id || '');
  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) || nodes[0] || null,
    [nodes, selectedNodeId],
  );
  const selectedEdges = useMemo(
    () => (selectedNode ? edges.filter((edge) => edge.to === selectedNode.id || edge.from === selectedNode.id) : []),
    [edges, selectedNode],
  );

  if (!summary || !nodes.length) {
    return (
      <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', color: 'var(--text-muted)' }}>
        Workflow node summary is not available for this template.
      </div>
    );
  }

  return (
    <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', display: 'grid', gap: '0.75rem', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
        <strong style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}><Network size={15} /> Node Inspector</strong>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{summary.node_count ?? nodes.length} nodes · {edges.length} edges</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(180px, 100%), 1fr))', gap: '0.5rem' }}>
        <div style={{ display: 'grid', gap: '0.4rem', minWidth: 0 }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}><Braces size={14} /> Classes</span>
          <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
            {classEntries.slice(0, 10).map(([name, count]) => (
              <span key={name} style={{ border: '1px solid var(--border-color)', borderRadius: 999, padding: '0.18rem 0.45rem', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                {name}: {count}
              </span>
            ))}
          </div>
        </div>
        <div style={{ display: 'grid', gap: '0.4rem', minWidth: 0 }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}><GitBranch size={14} /> Placeholders</span>
          <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
            {(summary.placeholders || []).slice(0, 16).map((placeholder) => (
              <span key={placeholder} className="code-chip">{placeholder}</span>
            ))}
            {summary.placeholders?.length ? null : <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>None</span>}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))', gap: '0.75rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: '0.45rem', maxHeight: 230, overflow: 'auto', minWidth: 0 }}>
          {nodes.map((node) => {
            const active = selectedNode?.id === node.id;
            return (
              <button
                key={node.id}
                type="button"
                onClick={() => setSelectedNodeId(node.id)}
                style={{
                  alignItems: 'flex-start',
                  border: '1px solid',
                  borderColor: active ? 'rgba(124, 106, 255, 0.42)' : 'var(--border-color)',
                  background: active ? 'rgba(124, 106, 255, 0.12)' : 'rgba(255,255,255,0.02)',
                  borderRadius: 8,
                  padding: '0.55rem',
                  display: 'grid',
                  gap: '0.25rem',
                  textAlign: 'left',
                  minWidth: 0,
                }}
              >
                <strong style={{ color: 'var(--text-primary)', fontSize: '0.8rem' }}>#{node.id}</strong>
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.76rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{node.class_type}</span>
              </button>
            );
          })}
        </div>
        <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.65rem', display: 'grid', gap: '0.45rem', minWidth: 0, alignContent: 'start' }}>
          {selectedNode ? (
            <>
              <strong>#{selectedNode.id} {selectedNode.class_type}</strong>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>{selectedNode.inputs.length} inputs</span>
              <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                {selectedNode.inputs.map((input) => <span key={input} className="code-chip">{input}</span>)}
              </div>
              <div style={{ display: 'grid', gap: '0.25rem', color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                {selectedEdges.length ? selectedEdges.map((edge) => (
                  <span key={`${edge.from}-${edge.to}-${edge.input}`}>{edge.from}:{edge.output} {'->'} {edge.to}.{edge.input}</span>
                )) : <span>No linked edges for this node.</span>}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
