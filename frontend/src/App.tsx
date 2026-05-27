import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';

const Dashboard = lazy(() => import('./pages/Dashboard').then((module) => ({ default: module.Dashboard })));
const WildcardsPage = lazy(() => import('./pages/wildcards/WildcardsPage').then((module) => ({ default: module.WildcardsPage })));
const MoviePage = lazy(() => import('./pages/movie/MoviePage').then((module) => ({ default: module.MoviePage })));
const CardsPage = lazy(() => import('./pages/cards/CardsPage').then((module) => ({ default: module.CardsPage })));
const GalleryPage = lazy(() => import('./pages/GalleryPage').then((module) => ({ default: module.GalleryPage })));
const LibraryPage = lazy(() => import('./pages/LibraryPage').then((module) => ({ default: module.LibraryPage })));
const TrainingPage = lazy(() => import('./pages/TrainingPage').then((module) => ({ default: module.TrainingPage })));
const GenerationPage = lazy(() => import('./pages/GenerationPage').then((module) => ({ default: module.GenerationPage })));
const VideoPage = lazy(() => import('./pages/VideoPage').then((module) => ({ default: module.VideoPage })));
const StudioSettings = lazy(() => import('./pages/StudioSettings').then((module) => ({ default: module.StudioSettings })));
const CharacterSheetPage = lazy(() => import('./pages/CharacterSheetPage'));

function RouteFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', color: 'var(--text-secondary)' }}>
      <span style={{ fontSize: '1rem', fontWeight: 600 }}>Loading workspace...</span>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Suspense fallback={<RouteFallback />}><Dashboard /></Suspense>} />
          <Route path="wildcards/*" element={<Suspense fallback={<RouteFallback />}><WildcardsPage /></Suspense>} />
          <Route path="movie/*" element={<Suspense fallback={<RouteFallback />}><MoviePage /></Suspense>} />
          <Route path="cards/*" element={<Suspense fallback={<RouteFallback />}><CardsPage /></Suspense>} />
          <Route path="characters" element={<Suspense fallback={<RouteFallback />}><CharacterSheetPage /></Suspense>} />
          <Route path="gallery" element={<Suspense fallback={<RouteFallback />}><GalleryPage /></Suspense>} />
          <Route path="library" element={<Suspense fallback={<RouteFallback />}><LibraryPage /></Suspense>} />
          <Route path="training" element={<Suspense fallback={<RouteFallback />}><TrainingPage /></Suspense>} />
          <Route path="generation" element={<Suspense fallback={<RouteFallback />}><GenerationPage /></Suspense>} />
          <Route path="video" element={<Suspense fallback={<RouteFallback />}><VideoPage /></Suspense>} />
          <Route path="settings" element={<Suspense fallback={<RouteFallback />}><StudioSettings /></Suspense>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
