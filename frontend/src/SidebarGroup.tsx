import {useState, type ReactNode} from 'react';
import {preference, savePreference} from './preferences';

export function SidebarGroup({name, children, initialOpen = false}: {name: string; children: ReactNode; initialOpen?: boolean}) {
  const [open, setOpen] = useState(() => preference('section-' + name, initialOpen));
  return <details className="sidebar-group" open={open} onToggle={event => {
    const next = event.currentTarget.open;
    setOpen(next);
    savePreference('section-' + name, next);
  }}><summary>{name}</summary>{children}</details>;
}
