from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime

import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

class VisualWorkflowExtractor:
    """
    Service for extracting structured workflows logically from images using OCR.
    """

    def extract_visual_workflow(self, image_path: Path) -> dict:
        """
        Main entry point for visual extraction.
        Returns a dict with 'nodes', 'edges', and 'confidence'.
        """
        try:
            with Image.open(image_path) as img:
                # 1. OCR for all text and bounding boxes
                # Using 'data' output format to get bounding boxes for each word/line
                ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                
                # 2. Grouping logic (Heuristic-based)
                nodes = self._group_ocr_into_nodes(ocr_data)
                
                # 3. Edge Inference (Spatial Heuristic)
                edges = self._infer_edges(nodes)
                
                # 4. Confidence Calculation
                # Basic placeholder for confidence (based on Tesseract individual confidences)
                conf_values = [float(c) for c in ocr_data['conf'] if int(c) != -1]
                avg_conf = sum(conf_values) / len(conf_values) / 100.0 if conf_values else 0.5
                
                return {
                    "nodes": nodes,
                    "edges": edges,
                    "confidence": round(avg_conf, 2),
                    "extracted_at": datetime.now().isoformat()
                }

        except Exception as e:
            logger.error(f"Visual workflow extraction failed: {e}")
            return {"nodes": [], "edges": [], "confidence": 0, "error": str(e)}

    def _group_ocr_into_nodes(self, data: dict) -> list[dict]:
        """
        Groups words into logical 'nodes' based on proximity and line height.
        """
        nodes = []
        n_boxes = len(data['text'])
        
        current_node = None
        
        for i in range(n_boxes):
            text = data['text'][i].strip()
            if not text:
                continue
            
            x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
            conf = int(data['conf'][i])
            
            if conf < 10: # Skip low confidence words
                continue
                
            # Heuristic: If word is close to previous word on same line, merge into same node
            if current_node and abs(y - current_node['position']['y']) < h and abs(x - (current_node['position']['x'] + current_node['width'])) < (w * 2):
                current_node['label'] += f" {text}"
                current_node['width'] = (x + w) - current_node['position']['x']
                current_node['height'] = max(current_node['height'], h)
            else:
                if current_node:
                    nodes.append(current_node)
                
                current_node = {
                    "id": str(len(nodes) + 1),
                    "label": text,
                    "type": "default",
                    "position": {"x": x, "y": y},
                    "width": w,
                    "height": h
                }
        
        if current_node:
            nodes.append(current_node)
            
        return nodes

    def _infer_edges(self, nodes: list[dict]) -> list[dict]:
        """
        Basic edge inference: Connect nodes that are vertically aligned or close horizontally.
        In a real scenario, this would look for lines or specific UI patterns.
        """
        edges = []
        # Simple heuristic: Connect sequential nodes if they are reasonably close
        for i in range(len(nodes) - 1):
            n1 = nodes[i]
            n2 = nodes[i+1]
            
            dx = n2['position']['x'] - n1['position']['x']
            dy = n2['position']['y'] - n1['position']['y']
            
            # If next node is to the right and not too far down
            if 0 < dx < 300 and abs(dy) < 50:
                edges.append({"id": f"e{n1['id']}-{n2['id']}", "source": n1['id'], "target": n2['id']})
                
        return edges

# Global instance for easy import
workflow_extractor = VisualWorkflowExtractor()
