import {getLibrary} from './api';

export function preference<T>(name: string, fallback: T): T {
  try {
    const value = localStorage.getItem(`liquidframe:${getLibrary()}:${name}`);
    return value === null ? fallback : JSON.parse(value);
  } catch { return fallback; }
}

export function savePreference(name: string, value: unknown) {
  try { localStorage.setItem(`liquidframe:${getLibrary()}:${name}`, JSON.stringify(value)); }
  catch { /* Browsing remains available when storage is full or disabled. */ }
}
