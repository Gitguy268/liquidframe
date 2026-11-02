import { getLibrary, type Selection } from './api';
export function openPhotobook(selection?: Selection) {
  const fragment = selection ? '#import=' + encodeURIComponent(JSON.stringify({library:getLibrary(),selection})) : '';
  window.open('/photobook/' + fragment, '_blank', 'noopener,noreferrer');
}
