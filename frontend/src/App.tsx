import type { ReactNode } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { activeAccessToken } from "./auth/session";
import { NotificationProvider } from "./components/layout/Notifications";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { MachinePage } from "./pages/MachinePage";
import { OrderDetailPage, OrdersPage, ProfilePage, QuoteHistoryPage, QuotesPage, ServicePage } from "./pages/RecordsPages";

function RequireSession({ children }: { children: ReactNode }) {
  return activeAccessToken() ? children : <Navigate to="/login" replace />;
}

function MachineRoute() {
  const { qrValue } = useParams();
  return activeAccessToken() ? <MachinePage /> : <LoginPage qrValue={qrValue} />;
}

export default function App() {
  return <NotificationProvider><Routes>
    <Route path="/" element={<Navigate to="/login" replace />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/machines/:qrValue" element={<MachineRoute />} />
    <Route path="/home" element={<RequireSession><HomePage /></RequireSession>} />
    <Route path="/orders" element={<RequireSession><OrdersPage /></RequireSession>} />
    <Route path="/orders/:orderId" element={<RequireSession><OrderDetailPage /></RequireSession>} />
    <Route path="/quotes/:quoteId" element={<RequireSession><QuoteHistoryPage /></RequireSession>} />
    <Route path="/quotes" element={<RequireSession><QuotesPage /></RequireSession>} />
    <Route path="/service" element={<RequireSession><ServicePage /></RequireSession>} />
    <Route path="/profile" element={<RequireSession><ProfilePage /></RequireSession>} />
    <Route path="*" element={<Navigate to="/login" replace />} />
  </Routes></NotificationProvider>;
}
