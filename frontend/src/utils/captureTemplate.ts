import html2canvas from 'html2canvas';

export async function captureTemplateForControlNet(): Promise<string | null> {
  const element = document.getElementById('character-template-preview');
  if (!element) {
    console.error('Template preview element not found');
    return null;
  }
  
  try {
    // We use a lower scale to keep the image size reasonable for ControlNet input
    const canvas = await html2canvas(element, { scale: 1, useCORS: true }); 
    return canvas.toDataURL('image/png');
  } catch (error) {
    console.error('Failed to capture template for ControlNet:', error);
    return null;
  }
}
