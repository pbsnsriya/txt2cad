import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/index.css';
import { App } from './app/App';
import { DesignPage } from './design/DesignPage';

// #/design shows the design-system check page; everything else is the app.
const Page = location.hash === '#/design' ? DesignPage : App;
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
