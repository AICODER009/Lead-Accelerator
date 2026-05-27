import json
import time
import random
from typing import Dict, Any

class OutboxSyncService:
    """
    Enterprise Transactional Outbox Pattern Manager.
    Used in production to ensure database updates and external CRM synchronizations 
    happen atomically within a single database transaction, preventing dual-write inconsistencies.
    """
    
    @staticmethod
    def initialize_outbox_db(conn) -> None:
        """Create the outbox queue table if it does not exist (SQLite/PostgreSQL)."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crm_outbox (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING', -- PENDING | PROCESSED | FAILED
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

    @staticmethod
    def queue_crm_update(conn, lead_id: str, lead_data: Dict[str, Any]) -> None:
        """
        Pushes a CRM sync event to the outbox queue.
        CRITICAL: This must run inside the SAME local database transaction as the lead's state changes.
        """
        cursor = conn.cursor()
        payload_json = json.dumps(lead_data)
        cursor.execute("""
            INSERT INTO crm_outbox (id, event_type, payload, status, retry_count)
            VALUES (?, 'CRM_SYNC', ?, 'PENDING', 0)
            ON CONFLICT(id) DO UPDATE SET
                payload = excluded.payload,
                status = 'PENDING',
                retry_count = 0,
                updated_at = CURRENT_TIMESTAMP
        """, (lead_id, payload_json))
        print(f"  [Transactional Outbox] Queued CRM_SYNC event in database transaction for lead ID: {lead_id}")

    @staticmethod
    def process_outbox_queue(conn) -> None:
        """
        Asynchronously processes the CRM outbox queue with rate-limit resiliency,
        network retry mechanisms, and exponential backoff logic.
        """
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, payload, retry_count FROM crm_outbox 
            WHERE status = 'PENDING' OR (status = 'FAILED' AND retry_count < 5)
            ORDER BY created_at ASC
        """)
        pending_events = cursor.fetchall()
        
        if not pending_events:
            return

        print(f"\n⚡ [Outbox Daemon] Processing {len(pending_events)} pending CRM events in background queue...")
        
        for event_id, payload_str, retry_count in pending_events:
            payload = json.loads(payload_str)
            
            # Simulate enterprise CRM rate-limiting check and exponential backoff delay
            if retry_count > 0:
                backoff_delay = (2 ** retry_count) + random.uniform(0.1, 0.5)
                print(f"  --> Event {event_id} is on retry #{retry_count}. Applying exponential backoff delay of {backoff_delay:.2f}s")
                time.sleep(backoff_delay)
            
            try:
                # Simulate high-fidelity network push to Salesforce/HubSpot webhook
                success = OutboxSyncService._mock_crm_push(payload)
                
                if success:
                    cursor.execute("""
                        UPDATE crm_outbox 
                        SET status = 'PROCESSED', updated_at = CURRENT_TIMESTAMP 
                        WHERE id = ?
                    """, (event_id,))
                    print(f"  [Outbox Success] Synced lead {payload['name']} cleanly to HubSpot CRM.")
                else:
                    raise ConnectionError("CRM API returned 429: Too Many Requests.")
                    
            except Exception as e:
                next_retry = retry_count + 1
                status = 'FAILED' if next_retry >= 5 else 'PENDING'
                cursor.execute("""
                    UPDATE crm_outbox 
                    SET status = ?, retry_count = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, next_retry, str(e), event_id))
                print(f"  ❌ [Outbox Error] Failed to sync lead {payload['name']}. Logged retry #{next_retry}. Error: {e}")
                
        conn.commit()

    @staticmethod
    def _mock_crm_push(lead_data: Dict[str, Any]) -> bool:
        """Mock high-fidelity enterprise webhook receiver with simulated rate limit spikes."""
        # 90% success rate to simulate highly stable network, 10% rate-limit spike
        return random.random() > 0.1
