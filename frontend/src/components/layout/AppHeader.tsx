import { useNavigate } from "react-router-dom";
import { activeUserId, clearSession } from "../../auth/session";
import { useNotifications } from "./Notifications";

export function AppHeader() {
  const navigate = useNavigate();
  const userId = activeUserId();
  const { notify } = useNotifications();
  function logout() { clearSession(); notify("You have been signed out.", "info"); navigate("/login"); }
  return <header className="app-header">
    <button className="wordmark" type="button" onClick={() => navigate("/home")} aria-label="Go to home">AROL</button>
    <nav className="header-nav" aria-label="Main navigation">
      <button type="button" onClick={() => navigate("/orders")}>Orders</button>
      <button type="button" onClick={() => navigate("/quotes")}>Quotes</button>
      <button type="button" onClick={() => navigate("/service")}>Support</button>
      <button type="button" onClick={() => navigate("/profile")}>Profile</button>
    </nav>
    <div className="header-actions"><span>{userId}</span><button className="text-button" type="button" onClick={logout}>Sign Out</button></div>
  </header>;
}
