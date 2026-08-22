import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "arol_fleet.db")

class ArolDatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def get_machine_telemetry(self, user_company_id: str, user_visibility: str, machine_id: str):
        if user_visibility not in ['full', 'technician']:
            return {
                "error": "ACCESS_DENIED",
                "message": f"The user with visibility '{user_visibility}' is not authorized to access operational/telemetric data."
            }
        
        conn = self._get_connection()

        query = """
            SELECT t.*
            FROM TelemetrySnapshots t
            JOIN Machines m ON t.machineId = m.machineId
            WHERE m.companyId = ? AND t.machineId = ?
            ORDER BY t.timestamp DESC
            LIMIT 10;
        """

        df = pd.read_sql_query(query, conn, params=(user_company_id, machine_id))
        conn.close()

        if df.empty:
            return {"message": "No telemetry data found, or machine belongs to another company."}
        
        return df.to_dict(orient="records")
    
    def get_machine_maintenance_history(self, user_company_id: str, user_visibility: str, machine_id: str):
        if user_visibility not in ['full', 'technician']:
            return {
                "error": "ACCESS_DENIED",
                "message": "Insufficient permissions for maintenance data."
            }
        
        conn = self._get_connection()

        query = """
            SELECT
                ticket.ticketId;
                ticket.ticketType,
                ticket.ticketStatus,
                ticket.createdDate,
                alarm.alarmCode,
                alarm.severity
            FROM MaintenanceTickets ticket
            JOIN Machines m ON ticket.machineId = m.machineId
            LEFT JOIN Alarms alarm ON ticket.alarmId = alarm.alarmId
            WHERE m.companyId = ? AND ticket.machineId = ?;
        """

        df = pd.read_sql_query(query, conn, params=(user_company_id, machine_id))
        conn.close()

        return df.to_dict(orient="records")
    
    def get_machine_details(self, user_company_id: str, machine_id: str):
        """
        Recupera le informazioni anagrafiche e la configurazione di una macchina.
        Disponibile per TUTTI i ruoli (full, technician, commercial) purche appartenga all'azienda.
        """
        conn = self._get_connection()
        query = """
            SELECT 
                m.machineId,
                m.serialNumber,
                m.deliveryDate,
                m.plantLocation,
                m.configurationProfile,
                m.plcFamily,
                mm.modelCode,
                mm.description AS modelDescription
            FROM Machines m
            LEFT JOIN MachineModels mm ON m.modelId = mm.modelId
            WHERE m.companyId = ? AND m.machineId = ?;
        """
        df = pd.read_sql_query(query, conn, params=(user_company_id, machine_id))
        conn.close()

        if df.empty:
            return {"error": "NOT_FOUND", "message": "Macchina non trovata o appartenente ad un'altra azienda."}[cite: 2]

        return df.to_dict(orient="records")[0]

    def get_commercial_quotes(self, user_company_id: str, user_visibility: str, machine_id: str = None):
        """
        Recupera preventivi, revisioni e righe d'ordine.
        ACCESSIBILE SOLO A: 'full' e 'commercial'.
        """
        # 1. Enforcement Sicurezza: Un 'technician' DEVE essere bloccato!
        if user_visibility not in ['full', 'commercial']:
            return {
                "error": "ACCESS_DENIED",
                "message": f"L'utente con visibilita '{user_visibility}' NON ha i permessi per accedere ai dati commerciali/preventivi."
            }[cite: 2]

        conn = self._get_connection()

        # Query che ricostruisce la storia commerciale tramite le revisioni dei preventivi
        query = """
            SELECT 
                q.quoteId,
                qr.revisionNumber,
                qr.revisionStatus,
                qr.totalAmount,
                ql.description AS lineDescription,
                ql.price
            FROM Quotes q
            JOIN QuoteRevisions qr ON q.quoteId = qr.quoteId
            LEFT JOIN QuoteLines ql ON qr.quoteRevisionId = ql.quoteRevisionId
            WHERE q.companyId = ?
        """
        params = [user_company_id]

        # Se e richiesto il dettaglio per una specifica macchina
        if machine_id:
            query += " AND ql.machineId = ?"
            params.append(machine_id)

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        return df.to_dict(orient="records")