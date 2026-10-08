import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import '../../src/styles.css';
import { createRoot } from 'react-dom/client';
import App from '../../src/App';
const addControl = maplibregl.Map.prototype.addControl;
maplibregl.Map.prototype.addControl = function (...args) {
  Object.assign(window, { dataMap: this });
  return addControl.apply(this, args);
};
createRoot(document.getElementById('root')!).render(<App />);
