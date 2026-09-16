import { useEffect } from 'react';
import '../styles/Toast.css';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastMessage {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastProps {
  toast: ToastMessage;
  onClose: (id: string) => void;
}

export const Toast: React.FC<ToastProps> = ({ toast, onClose }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose(toast.id);
    }, 4000);

    return () => clearTimeout(timer);
  }, [toast.id, onClose]);

  const icons: Record<ToastType, string> = {
    success: '✓',
    error: '✕',
    info: 'ⓘ',
    warning: '⚠',
  };

  return (
    <div className={`toast toast-${toast.type}`} role="status" aria-live="polite">
      <div className="toast-content">
        <span className="toast-icon">{icons[toast.type]}</span>
        <span className="toast-message">{toast.message}</span>
      </div>
      <button
        className="toast-close"
        onClick={() => onClose(toast.id)}
        aria-label="Close notification"
      >
        ×
      </button>
    </div>
  );
};

export const ToastContainer: React.FC<{
  toasts: ToastMessage[];
  onClose: (id: string) => void;
}> = ({ toasts, onClose }) => (
  <div className="toast-container">
    {toasts.map((toast) => (
      <Toast key={toast.id} toast={toast} onClose={onClose} />
    ))}
  </div>
);
