import { useUiPreferences } from './hooks/useUiPreferences';

type Dictionary = Record<string, string>;

const en: Dictionary = {
  // Navigation & Layout
  'nav.dashboard': 'Dashboard',
  'nav.movie': 'Movie Script',
  'nav.cards': 'SillyTavern Cards',
  'nav.characters': 'Character Sheet',
  'nav.wildcards': 'Wildcards',
  'nav.gallery': 'Gallery',
  'nav.library': 'Library',
  'nav.training': 'Training',
  'nav.generation': 'Generation',
  'nav.video': 'Video',
  'nav.settings': 'Settings',
  'nav.language': 'Language',
  'nav.theme': 'Theme',
  'nav.active_studio': 'Studio Active',
  'theme.dark': 'Dark',
  'theme.light': 'Light',
  
  // Dashboard
  'dashboard.workspace_modules': 'Workspace Modules',
  
  // Gallery Page
  'gallery.loaded': '{{count}} / {{total}} loaded',
  'gallery.loaded_simple': '{{count}} loaded',
  'gallery.zoom_info': 'Zoom Image Info',
  'gallery.readonly_source': 'Read-only mounted source',
  'gallery.title': 'Media Explorer & Comparer',
  'gallery.subtitle': 'items mapped · read-only indexing for mounted folders',
  'gallery.shortcuts': 'Shortcuts',
  'gallery.searchAssets': 'Search indexed assets...',
  'gallery.refresh': 'Refresh',
  'gallery.uploadImages': 'Upload Images',
  'gallery.uploadFolder': 'Upload Folder',
  'gallery.allAssets': 'All Assets',
  'gallery.indexedSources': 'Indexed Sources',
  'gallery.collections': 'Collections',
  'gallery.scanBasic': 'Basic Index',
  'gallery.scanMetadata': 'Scan Metadata',
  'gallery.scanAi': 'CLIP / AI Scan',
  'gallery.library': 'Library',
  'gallery.filters': 'Filters',
  'gallery.scanCenter': 'Scan Center',
  'gallery.loadMore': 'Load More',
  'gallery.openDetails': 'Open image details',
  'gallery.addSelection': 'Add to selection',
  'gallery.removeSelection': 'Remove from selection',
  'gallery.addCollection': 'Add to collection',
  'gallery.addNsfw': 'Add NSFW tag',
  'gallery.basicIndexFile': 'Basic index this file',
  'gallery.visionLlmScan': 'Scan with Vision LLM (KoboldCpp)',
  'gallery.copyPromptTags': 'Copy prompt tags',
  'gallery.exportWorkflow': 'Export workflow JSON',
  'gallery.sendWildcards': 'Send to Wildcards',
  'gallery.openOriginal': 'Open original image',
  'gallery.viewControls': 'View Controls',
  'gallery.hideNsfw': 'Hide NSFW',
  'gallery.liveIndexed': 'Live + Indexed',
  'gallery.indexedOnly': 'Indexed only',
  'gallery.pageSize': 'Page size',
  'gallery.chooseCollection': 'Add to Collection...',
  'gallery.selectedCount': 'selected',
  'gallery.bulkAddTag': 'Bulk Add Tag',
  'gallery.addNsfwSelected': 'Mark NSFW',
  'gallery.clearSelection': 'Clear Selection',
  'gallery.compareSelected': 'Compare Selected',

  // Cards
  'cards.generate_world_image': 'Generate World Image',
};

const fr: Dictionary = {
  // Navigation & Layout
  'nav.dashboard': 'Tableau',
  'nav.movie': 'Scénario de Film',
  'nav.cards': 'Cartes SillyTavern',
  'nav.characters': 'Fiche de Personnage',
  'nav.wildcards': 'Wildcards',
  'nav.gallery': 'Galerie',
  'nav.library': 'Bibliothèque',
  'nav.training': 'Entraînement',
  'nav.generation': 'Génération',
  'nav.video': 'Vidéo',
  'nav.settings': 'Réglages',
  'nav.language': 'Langue',
  'nav.theme': 'Thème',
  'nav.active_studio': 'Studio actif',
  'theme.dark': 'Sombre',
  'theme.light': 'Clair',

  // Dashboard
  'dashboard.workspace_modules': 'Modules de l\'Espace de Travail',

  // Gallery Page
  'gallery.loaded': '{{count}} / {{total}} chargés',
  'gallery.loaded_simple': '{{count}} chargés',
  'gallery.zoom_info': 'Zoomer les infos',
  'gallery.readonly_source': 'Source montée en lecture seule',
  'gallery.title': 'Galerie et comparateur',
  'gallery.subtitle': 'éléments indexés · indexation en lecture seule',
  'gallery.shortcuts': 'Raccourcis',
  'gallery.searchAssets': 'Rechercher dans la galerie...',
  'gallery.refresh': 'Rafraîchir',
  'gallery.uploadImages': 'Importer images',
  'gallery.uploadFolder': 'Importer dossier',
  'gallery.allAssets': 'Tous les assets',
  'gallery.indexedSources': 'Sources indexées',
  'gallery.collections': 'Collections',
  'gallery.scanBasic': 'Index simple',
  'gallery.scanMetadata': 'Scan metadata',
  'gallery.scanAi': 'Scan CLIP / IA',
  'gallery.library': 'Bibliothèque',
  'gallery.filters': 'Filtres',
  'gallery.scanCenter': 'Centre de scan',
  'gallery.loadMore': 'Charger plus',
  'gallery.openDetails': 'Ouvrir les détails',
  'gallery.addSelection': 'Ajouter à la sélection',
  'gallery.removeSelection': 'Retirer de la sélection',
  'gallery.addCollection': 'Ajouter à une collection',
  'gallery.addNsfw': 'Ajouter tag NSFW',
  'gallery.basicIndexFile': 'Indexer ce fichier',
  'gallery.visionLlmScan': 'Scanner avec Vision LLM (KoboldCpp)',
  'gallery.copyPromptTags': 'Copier les tags du prompt',
  'gallery.exportWorkflow': 'Exporter le workflow JSON',
  'gallery.sendWildcards': 'Envoyer vers Wildcards',
  'gallery.openOriginal': 'Ouvrir l\'image originale',
  'gallery.viewControls': 'Contrôles de vue',
  'gallery.hideNsfw': 'Masquer NSFW',
  'gallery.liveIndexed': 'Live + Indexé',
  'gallery.indexedOnly': 'Indexé seulement',
  'gallery.pageSize': 'Taille page',
  'gallery.chooseCollection': 'Ajouter à une collection...',
  'gallery.selectedCount': 'sélectionnés',
  'gallery.bulkAddTag': 'Taguer en masse',
  'gallery.addNsfwSelected': 'Marquer NSFW',
  'gallery.clearSelection': 'Vider sélection',
  'gallery.compareSelected': 'Comparer sélection',

  // Cards
  'cards.generate_world_image': 'Générer l\'Image du Monde',
};

const dictionaries: Record<'en' | 'fr', Dictionary> = { en, fr };

export function useTranslation() {
  const { language } = useUiPreferences();
  
  const t = (key: string, params?: Record<string, string | number>) => {
    const dict = dictionaries[language] || dictionaries.en;
    let translation = dict[key] || dictionaries.en[key] || key;
    
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        translation = translation.replace(`{{${k}}}`, String(v));
      }
    }
    
    return translation;
  };
  
  return { t };
}
