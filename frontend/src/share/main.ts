import { loadModel, UnsupportedBrowser } from './data';
import { startViewer, type ShareViewer } from './viewer';
import './share.css';

declare global { interface Window { txt2cadShare?: ShareViewer } }

async function main(): Promise<void> {
  const loading = document.getElementById('loading');
  const source = document.getElementById('model-data');
  try {
    if (!source) throw new Error('This file has no model in it.');
    const data = await loadModel(source.textContent ?? '');
    window.txt2cadShare = startViewer(data);
  } catch (e) {
    if (loading) {
      loading.hidden = false;
      loading.setAttribute('role', 'alert');
      loading.textContent = e instanceof UnsupportedBrowser ? e.message : `The model could not be shown: ${(e as Error).message}`;
    }
  }
}

void main();
