import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/index.css';
import { DesignPage } from './design/DesignPage';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DesignPage />
  </StrictMode>,
);
