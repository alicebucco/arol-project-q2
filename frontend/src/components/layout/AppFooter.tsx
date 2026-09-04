export function AppFooter() {
  return <footer className="app-footer">
    <div className="footer-main"><div className="footer-identity">
      <a className="footer-wordmark" href="https://www.arol.com" target="_blank" rel="noreferrer">AROL</a>
      <p>AROL S.P.A. – Viale Italia, 193 · 14053 Canelli (Asti), Italy</p><p>Tax ID and VAT no. 03217610967 · REA AT 108104</p>
    </div><nav className="footer-nav" aria-label="AROL links">
      <a href="https://www.arol.com/arol-canelli" target="_blank" rel="noreferrer">Company</a><a href="https://www.arol.com/?Itemid=689" target="_blank" rel="noreferrer">Customer Care</a><a href="https://www.arol.com/arol-work-with-us" target="_blank" rel="noreferrer">Work with us</a><a href="https://www.arol.com/arol-contact" target="_blank" rel="noreferrer">Contacts</a>
    </nav></div>
    <div className="footer-legal"><span>© {new Date().getFullYear()} AROL S.P.A.</span><div>
      <a href="https://www.arol.com/terms-condition" target="_blank" rel="noreferrer">Terms &amp; Conditions</a><a href="https://www.arol.com/legal-notes" target="_blank" rel="noreferrer">Legal Notice</a><a href="https://www.privacylab.it/informativa.php?12701471129&lang=en" target="_blank" rel="noreferrer">Privacy Policy</a>
    </div></div>
  </footer>;
}
