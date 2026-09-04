import { useEffect, useRef, useState } from "react";
import { BrowserQRCodeReader } from "@zxing/browser";

export function QrScanner({ onClose, onDetected }: { onClose: () => void; onDetected: (value: string) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null); const [error, setError] = useState(""); const [status, setStatus] = useState("Starting camera…");
  useEffect(() => {
    const reader = new BrowserQRCodeReader(); let active = true; let hasDetected = false; let stream: MediaStream | undefined; let stopScanner: (() => void) | undefined; let noResultTimer: number | undefined; let detectedTimer: number | undefined;
    async function startScanner() {
      if (!videoRef.current || !navigator.mediaDevices?.getUserMedia) { setError("The camera is not supported by this browser."); return; }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false }); videoRef.current.srcObject = stream; await videoRef.current.play(); if (!active) return;
        setStatus("Point the camera at the machine QR code."); noResultTimer = window.setTimeout(() => { if (active && !hasDetected) setStatus("Camera is active, but no QR code has been detected yet."); }, 5_000);
        const controls = await reader.decodeFromStream(stream, videoRef.current, (result) => { const value = result?.getText().trim(); if (active && !hasDetected && value) { hasDetected = true; window.clearTimeout(noResultTimer); setStatus(`QR code detected: ${value}. Opening machine…`); detectedTimer = window.setTimeout(() => onDetected(value), 350); } });
        stopScanner = () => controls.stop(); if (!active) stopScanner();
      } catch (scanError) { if (!active) return; if (scanError instanceof DOMException && scanError.name === "NotAllowedError") setError("Camera access was denied. Allow camera access in your browser and try again."); else setError("Unable to start the camera. Check that it is not being used by another application."); }
    }
    startScanner(); return () => { active = false; window.clearTimeout(noResultTimer); window.clearTimeout(detectedTimer); stopScanner?.(); stream?.getTracks().forEach((track) => track.stop()); if (videoRef.current) videoRef.current.srcObject = null; };
  }, [onDetected]);
  return <div className="qr-scanner-backdrop" role="presentation" onClick={onClose}><section className="qr-scanner-dialog" role="dialog" aria-modal="true" aria-labelledby="qr-scanner-title" onClick={(event) => event.stopPropagation()}>
    <div className="qr-scanner-heading"><div><p className="eyebrow dark-eyebrow">QR SCANNER</p><h2 id="qr-scanner-title">Scan the QR code</h2></div><button className="chat-close-button" type="button" onClick={onClose} aria-label="Close scanner">×</button></div>
    <p className="qr-scanner-status" role="status">{status}</p>{!error && <video className="qr-video" ref={videoRef} autoPlay muted playsInline />}{error && <p className="status-message error-message">{error}</p>}{!error && <p className="qr-scanner-help">Keep the entire QR code in the frame, well lit and free of reflections. If it is not read after a few seconds, move the code closer or farther away.</p>}<button className="qr-scanner-close" type="button" onClick={onClose}>Cancel</button>
  </section></div>;
}
