import { useState } from "react";
import type { FormEvent } from "react";
import { apiPost, fetchManualPdf, readableError } from "../../api/client";
import type { ChatHistoryTurn, ChatMessage, ChatResponse, ManualSearchResult } from "../../types";
import { manualRelevanceLabel } from "../../utils/format";
import { useNotifications } from "../layout/Notifications";
import { ChatStructuredData } from "./ChatStructuredData";

export function AssistantChat({ machineId, onClose }: { machineId: string; onClose: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]); const [draft, setDraft] = useState(""); const [error, setError] = useState(""); const [isSending, setIsSending] = useState(false); const [openingSource, setOpeningSource] = useState<string | null>(null); const { notify } = useNotifications();
  function conversationHistory(): ChatHistoryTurn[] {
    let lastAssistant = -1;
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === "assistant") { lastAssistant = index; break; }
    }
    return (lastAssistant < 0 ? [] : messages.slice(0, lastAssistant + 1).slice(-8)).map(({ role, content }) => ({ role, content }));
  }
  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const message = draft.trim(); if (!message || isSending) return;
    const userMessage: ChatMessage = { id: Date.now(), role: "user", content: message }; setMessages((current) => [...current, userMessage]); setDraft(""); setError(""); setIsSending(true);
    try { const result = await apiPost<ChatResponse>("/chat", { message, machine_id: machineId, history: conversationHistory() }); setMessages((current) => [...current, { id: Date.now() + 1, role: "assistant", content: result.answer, agent: result.agent, sources: result.sources, data: result.data }]); }
    catch (sendError) { const errorMessage = readableError(sendError, "Unable to send the question."); setError(errorMessage); notify(errorMessage, "error"); }
    finally { setIsSending(false); }
  }
  async function openManualSource(source: ManualSearchResult, sourceKey: string) {
    const manualWindow = window.open("", "_blank"); if (!manualWindow) { const message = "Your browser blocked the new tab. Allow pop-ups for this site and try again."; setError(message); notify(message, "error"); return; }
    setError(""); setOpeningSource(sourceKey);
    try { const pdf = await fetchManualPdf(machineId, source.citation.file); const pdfUrl = URL.createObjectURL(pdf); manualWindow.location.href = `${pdfUrl}#page=${source.citation.page}`; window.setTimeout(() => URL.revokeObjectURL(pdfUrl), 60_000); notify(`Opening ${source.citation.file} at page ${source.citation.page}.`, "success"); }
    catch (openError) { manualWindow.close(); const message = readableError(openError, "Unable to open the manual."); setError(message); notify(message, "error"); }
    finally { setOpeningSource(null); }
  }
  return <><div className="chat-drawer-backdrop" aria-hidden="true" onClick={onClose} /><section className="assistant-chat" role="dialog" aria-modal="true" aria-labelledby="assistant-chat-title"><div className="assistant-chat-heading"><div><p className="eyebrow dark-eyebrow">AROL ASSISTANT</p><h2 id="assistant-chat-title">Ask about this machine</h2></div><div className="chat-heading-actions"><span className="chat-machine-context">{machineId}</span><button className="chat-close-button" type="button" onClick={onClose} aria-label="Close chat">×</button></div></div><p className="chat-intro">Ask about alarms, telemetry, maintenance, manuals, orders and quotes.</p><div className="chat-history" aria-live="polite">{messages.length === 0 && <p className="chat-empty">For example: “Are there any recent alarms?” or “Find safety instructions in the manual”.</p>}{messages.map((message) => <article key={message.id} className={`chat-message chat-message-${message.role}`}><span className="chat-message-label">{message.role === "user" ? "You" : "AROL Assistant"}</span><p>{message.content}</p>{message.sources && message.sources.length > 0 && <div className="chat-manual-sources" aria-label="Manual sources">{message.sources.map((source, index) => <article className="chat-manual-source" key={`${source.citation.file}-${source.citation.page}-${index}`}><div className="chat-manual-source-heading"><strong>{source.title}</strong><span>{manualRelevanceLabel(source.relevance)}</span></div><p>{source.excerpt}</p>{source.highlights.length > 0 && <div className="chat-manual-highlights">{source.highlights.map((term) => <mark key={term}>{term}</mark>)}</div>}<div className="chat-manual-source-footer"><small>{source.citation.file} · Page {source.citation.page} · {source.citation.section}</small><button type="button" className="chat-open-manual-button" onClick={() => openManualSource(source, `${message.id}-${index}`)} disabled={openingSource !== null}>{openingSource === `${message.id}-${index}` ? "Opening…" : "Open source"}</button></div></article>)}</div>}{message.data && <ChatStructuredData data={message.data} />}{message.agent && message.agent.length > 0 && <small>Agent: {message.agent.join(", ")}</small>}</article>)}{isSending && <p className="chat-thinking">AROL Assistant is preparing a response…</p>}</div>{error && <p className="status-message error-message">{error}</p>}<form className="chat-form" onSubmit={sendMessage}><label className="sr-only" htmlFor="chat-message">Question for AROL Assistant</label><textarea id="chat-message" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Write a question about this machine…" rows={3} disabled={isSending} /><button type="submit" disabled={isSending || !draft.trim()}>{isSending ? "Sending…" : "Send question"}</button></form></section></>;
}
