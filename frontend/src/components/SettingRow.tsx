import type { ReactNode } from 'react';

/** One setting on a row: what it is and what it does on the left, the control on the right. */
export function SettingRow({ title, help, children }: { title: string; help: string; children: ReactNode }) {
  return (
    <div className="setting-row">
      <div className="setting-row-text">
        <b>{title}</b>
        <p className="setting-row-help">{help}</p>
      </div>
      <div className="setting-row-control">{children}</div>
    </div>
  );
}
