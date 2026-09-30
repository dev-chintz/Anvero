import { useEffect, useState } from 'react';
import { ApiError, usersApi } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { SettingRow } from '../components/SettingRow';
import { useTranslation } from '../i18n';
import type { PermissionArea, PermissionGrant, PermissionLevel, Role, User } from '../types/user';

const AREAS: PermissionArea[] = ['orders', 'messages', 'after_sales', 'labels', 'finance', 'integrations'];
const MIN_PASSWORD_LENGTH = 12;

/** 'none' stands for no grant at all; the grid always has all six areas, unlike the list of grants a user carries. */
type LevelChoice = PermissionLevel | 'none';
type Grid = Record<PermissionArea, LevelChoice>;

function emptyGrid(): Grid {
  return Object.fromEntries(AREAS.map((area) => [area, 'none'])) as Grid;
}

function gridFromGrants(grants: PermissionGrant[]): Grid {
  const grid = emptyGrid();
  for (const grant of grants) grid[grant.area] = grant.level;
  return grid;
}

function grantsFromGrid(grid: Grid): PermissionGrant[] {
  return AREAS.filter((area) => grid[area] !== 'none').map((area) => ({
    area,
    level: grid[area] as PermissionLevel,
  }));
}

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

type Selection = { kind: 'existing'; user: User } | { kind: 'new' } | null;

/**
 * Accounts, their role and their permissions: a list on the left, the one chosen open on
 * the right, so switching between accounts needs no dialog (`docs/STYLE_GUIDE.md`, "Patterns
 * for a page of settings"). Only an administrator ever sees this tab (Settings.tsx). Role, state
 * and each permission are segmented choices, all in view (DECISIONS.md, 2026-10-01, "Users,
 * updates and the login page").
 */
export function UsersSettings() {
  const { t } = useTranslation();
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);

  const load = () => {
    usersApi
      .list()
      .then((list) => {
        setUsers(list);
        setLoadError(null);
        setSelection((current) => {
          if (current?.kind === 'existing') {
            const fresh = list.find((u) => u.id === current.user.id);
            if (fresh) return { kind: 'existing', user: fresh };
          }
          return current ?? (list.length > 0 ? { kind: 'existing', user: list[0] } : null);
        });
      })
      .catch((err: unknown) => setLoadError(messageOf(err, t('users.loadFailed'))));
  };

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (loadError) {
    return (
      <p role="alert" className="error-message">
        {loadError}
      </p>
    );
  }
  if (!users) return <p role="status">{t('users.loading')}</p>;

  return (
    <div className="users-settings">
      <div className="users-list card tone-blue">
        <div className="users-list-head">
          <h2>{t('users.title')}</h2>
          <button type="button" onClick={() => setSelection({ kind: 'new' })}>
            {t('users.addAccount')}
          </button>
        </div>
        {users.map((u) => (
          <button
            key={u.id}
            type="button"
            className={`user-row${selection?.kind === 'existing' && selection.user.id === u.id ? ' is-selected' : ''}`}
            onClick={() => setSelection({ kind: 'existing', user: u })}
          >
            <span className="user-row-email">
              {u.email}
              {u.id === me?.id && <> {t('users.you')}</>}
            </span>
            <span className="user-row-meta">
              <span className={`role-badge${u.role === 'admin' ? ' is-admin' : ''}`}>
                {t(u.role === 'admin' ? 'users.role.admin' : 'users.role.user')}
              </span>
              {!u.is_active && <span className="users-chip is-inactive">{t('users.status.inactive')}</span>}
            </span>
          </button>
        ))}
      </div>

      {selection?.kind === 'existing' ? (
        <UserPanel key={selection.user.id} user={selection.user} onSaved={load} />
      ) : selection?.kind === 'new' ? (
        <NewUserPanel onCreated={load} />
      ) : (
        <div className="card">
          <p className="field-note">{t('users.selectPrompt')}</p>
        </div>
      )}
    </div>
  );
}

/** A choice of a few values as one segmented control (a radio group). */
function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** The permission grid, shared by an existing account's panel and the new-account form. */
function PermissionGridEditor({ grid, onChange }: { grid: Grid; onChange: (grid: Grid) => void }) {
  const { t } = useTranslation();
  return (
    <div className="permission-grid">
      <p className="permission-grid-title">{t('users.permissions')}</p>
      {AREAS.map((area) => (
        <div key={area} className="permission-row">
          <span>{t(`users.area.${area}`)}</span>
          <Segmented<LevelChoice>
            label={t(`users.area.${area}`)}
            value={grid[area]}
            options={[
              { value: 'none', label: t('users.level.none') },
              { value: 'view', label: t('users.level.view') },
              { value: 'manage', label: t('users.level.manage') },
            ]}
            onChange={(level) => onChange({ ...grid, [area]: level })}
          />
        </div>
      ))}
    </div>
  );
}

function UserPanel({ user, onSaved }: { user: User; onSaved: () => void }) {
  const { t } = useTranslation();
  const [role, setRole] = useState<Role>(user.role);
  const [isActive, setIsActive] = useState(user.is_active);
  const [grid, setGrid] = useState<Grid>(() => gridFromGrants(user.permissions));
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password && password.length < MIN_PASSWORD_LENGTH) {
      setNote({ text: t('users.passwordTooShort', { count: String(MIN_PASSWORD_LENGTH) }), error: true });
      return;
    }
    setSaving(true);
    setNote(null);
    try {
      await usersApi.update(user.id, {
        role,
        is_active: isActive,
        permissions: role === 'admin' ? [] : grantsFromGrid(grid),
        ...(password ? { password } : {}),
      });
      setPassword('');
      setNote({ text: t('users.saved'), error: false });
      onSaved();
    } catch (err: unknown) {
      setNote({ text: messageOf(err, t('users.saveFailed')), error: true });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="card" onSubmit={handleSave}>
      <div className="card-head users-panel-head">
        <h2>{user.email}</h2>
        <span className={`users-chip ${user.is_active ? 'is-active' : 'is-inactive'}`}>
          {t(user.is_active ? 'users.status.active' : 'users.status.inactive')}
        </span>
      </div>

      <SettingRow title={t('users.roleLabel')} help={t('users.roleHelp')}>
        <Segmented<Role>
          label={t('users.roleLabel')}
          value={role}
          options={[
            { value: 'user', label: t('users.role.user') },
            { value: 'admin', label: t('users.role.admin') },
          ]}
          onChange={setRole}
        />
      </SettingRow>

      <SettingRow title={t('users.activeLabel')} help={t('users.activeHelp')}>
        <Segmented<'active' | 'inactive'>
          label={t('users.activeLabel')}
          value={isActive ? 'active' : 'inactive'}
          options={[
            { value: 'active', label: t('users.status.active') },
            { value: 'inactive', label: t('users.status.inactive') },
          ]}
          onChange={(state) => setIsActive(state === 'active')}
        />
      </SettingRow>

      <SettingRow title={t('users.password')} help={t('users.passwordHelpReset')}>
        <input
          type="password"
          aria-label={t('users.password')}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          placeholder={t('users.passwordUnchanged')}
        />
      </SettingRow>

      {role === 'user' ? (
        <PermissionGridEditor grid={grid} onChange={setGrid} />
      ) : (
        <p className="field-note">{t('users.adminHasEverything')}</p>
      )}

      {note && (
        <p role={note.error ? 'alert' : 'status'} className={note.error ? 'error-message' : ''}>
          {note.text}
        </p>
      )}

      <div className="users-actions">
        <button type="submit" className="is-primary" disabled={saving}>
          {saving ? t('users.saving') : t('users.save')}
        </button>
      </div>
    </form>
  );
}

function NewUserPanel({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<Role>('user');
  const [grid, setGrid] = useState<Grid>(emptyGrid);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim()) {
      setNote({ text: t('users.emailRequired'), error: true });
      return;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      setNote({ text: t('users.passwordTooShort', { count: String(MIN_PASSWORD_LENGTH) }), error: true });
      return;
    }
    setSaving(true);
    setNote(null);
    try {
      await usersApi.create({
        email: email.trim(),
        password,
        role,
        permissions: role === 'admin' ? [] : grantsFromGrid(grid),
      });
      setNote({ text: t('users.created'), error: false });
      setEmail('');
      setPassword('');
      onCreated();
    } catch (err: unknown) {
      const taken = err instanceof ApiError && err.status === 409;
      setNote({ text: taken ? t('users.emailTaken') : messageOf(err, t('users.createFailed')), error: true });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="card" onSubmit={handleCreate}>
      <div className="card-head users-panel-head">
        <h2>{t('users.newAccountTitle')}</h2>
      </div>

      <SettingRow title={t('users.email')} help="">
        <input
          type="email"
          aria-label={t('users.email')}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="off"
          placeholder="jan@example.com"
        />
      </SettingRow>

      <SettingRow title={t('users.password')} help={t('users.passwordHelpNew', { count: String(MIN_PASSWORD_LENGTH) })}>
        <input
          type="password"
          aria-label={t('users.password')}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
        />
      </SettingRow>

      <SettingRow title={t('users.roleLabel')} help={t('users.roleHelp')}>
        <Segmented<Role>
          label={t('users.roleLabel')}
          value={role}
          options={[
            { value: 'user', label: t('users.role.user') },
            { value: 'admin', label: t('users.role.admin') },
          ]}
          onChange={setRole}
        />
      </SettingRow>

      {role === 'user' ? (
        <PermissionGridEditor grid={grid} onChange={setGrid} />
      ) : (
        <p className="field-note">{t('users.adminHasEverything')}</p>
      )}

      {note && (
        <p role={note.error ? 'alert' : 'status'} className={note.error ? 'error-message' : ''}>
          {note.text}
        </p>
      )}

      <div className="users-actions">
        <button type="submit" className="is-primary" disabled={saving}>
          {saving ? t('users.saving') : t('users.create')}
        </button>
      </div>
    </form>
  );
}
