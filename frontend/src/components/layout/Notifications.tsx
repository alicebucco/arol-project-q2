import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";

type NotificationKind = "success" | "error" | "info";
type Notification = { id: number; kind: NotificationKind; message: string };
type NotificationContextValue = { notify: (message: string, kind?: NotificationKind) => void };
const NotificationContext = createContext<NotificationContextValue | null>(null);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const notify = useCallback((message: string, kind: NotificationKind = "info") => {
    const id = Date.now() + Math.floor(Math.random() * 1_000);
    setNotifications((current) => [...current, { id, kind, message }]);
    window.setTimeout(() => setNotifications((current) => current.filter((item) => item.id !== id)), 5_000);
  }, []);
  return <NotificationContext.Provider value={{ notify }}>
    {children}
    <div className="notification-stack" aria-live="polite" aria-atomic="true">
      {notifications.map((notification) => <div key={notification.id} className={`notification notification-${notification.kind}`} role="status">{notification.message}</div>)}
    </div>
  </NotificationContext.Provider>;
}

export function useNotifications() {
  const context = useContext(NotificationContext);
  if (context === null) throw new Error("Notifications must be used within NotificationProvider.");
  return context;
}
