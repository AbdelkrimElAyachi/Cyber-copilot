"""
FastAPI router for the investigations resource.
"""

import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from database import Database, new_id
from api.dependencies import (
    get_db,
    get_investigation_manager,
    get_ai_investigator,
    get_alert_receiver,
)

router = APIRouter(prefix="/investigations", tags=["investigations"])

# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class InvestigationUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    assigned_to: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None

class EvidenceCreate(BaseModel):
    source_type: str
    source_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    collected_by: Optional[str] = None

class AnalysisCreate(BaseModel):
    analysis_type: str = "ai"
    verdict: Optional[str] = None
    content: str
    confidence: Optional[float] = None
    model_id: Optional[str] = None
    created_by: Optional[str] = None

class ActionCreate(BaseModel):
    action_type: str
    description: str
    reasoning: Optional[str] = None
    performed_by: Optional[str] = None

class ActionUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[str] = None

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_investigation_exists(db: Database, investigation_id: str):
    row = db.fetchone("SELECT id FROM investigations WHERE id = %s", (investigation_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Investigation not found")

# ─────────────────────────────────────────────────────────────────────────────
# Routes - Investigations
# ─────────────────────────────────────────────────────────────────────────────

@router.get("")
def list_investigations(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Database = Depends(get_db)
):
    query = "SELECT * FROM investigations WHERE 1=1"
    params = []
    
    if status:
        query += " AND status = %s"
        params.append(status)
    if severity:
        query += " AND severity = %s"
        params.append(severity)
    if assigned_to:
        query += " AND assigned_to = %s"
        params.append(assigned_to)
        
    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    return db.fetchall(query, tuple(params))

@router.get("/{investigation_id}")
def get_investigation(investigation_id: str, db: Database = Depends(get_db)):
    row = db.fetchone("SELECT * FROM investigations WHERE id = %s", (investigation_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return row

@router.patch("/{investigation_id}")
def update_investigation(
    investigation_id: str, 
    update_data: InvestigationUpdate, 
    db: Database = Depends(get_db)
):
    _ensure_investigation_exists(db, investigation_id)
    
    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
        return db.fetchone("SELECT * FROM investigations WHERE id = %s", (investigation_id,))
        
    set_clauses = []
    params = []
    for key, value in update_dict.items():
        set_clauses.append(f"{key} = %s")
        params.append(value)
        
    query = f"UPDATE investigations SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = %s"
    params.append(investigation_id)
    
    db.execute(query, tuple(params))
    return db.fetchone("SELECT * FROM investigations WHERE id = %s", (investigation_id,))

@router.delete("/{investigation_id}", status_code=204)
def delete_investigation(investigation_id: str, db: Database = Depends(get_db)):
    """Delete an investigation and everything filed under it.

    There's no ON DELETE CASCADE on these tables, so child rows
    (evidence/analysis/actions) are removed first, then the
    investigation itself.
    """
    _ensure_investigation_exists(db, investigation_id)
    db.execute("DELETE FROM investigation_evidence WHERE investigation_id = %s", (investigation_id,))
    db.execute("DELETE FROM investigation_analysis WHERE investigation_id = %s", (investigation_id,))
    db.execute("DELETE FROM investigation_actions WHERE investigation_id = %s", (investigation_id,))
    db.execute("DELETE FROM investigations WHERE id = %s", (investigation_id,))
    return None

@router.post("/{investigation_id}/investigate", status_code=202)
def trigger_investigation(
    investigation_id: str,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
    investigator=Depends(get_ai_investigator),
    receiver=Depends(get_alert_receiver),
):
    """(Re-)run the AI Investigator on this investigation's triggering alert.

    Runs in the background — poll GET /investigations/{id} or its
    /analysis endpoint for the result.
    """
    inv = db.fetchone(
        "SELECT id, alert_id, status FROM investigations WHERE id = %s",
        (investigation_id,),
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if inv["status"] == "IN_PROGRESS":
        raise HTTPException(status_code=409, detail="Investigation is already running")
    if investigator is None:
        raise HTTPException(status_code=503, detail="AI Investigator is not configured")
    if not inv["alert_id"]:
        raise HTTPException(status_code=400, detail="Investigation has no linked alert")
    if receiver is None:
        raise HTTPException(status_code=503, detail="Wazuh Indexer is not configured")

    alert = receiver.get_alert_by_id(inv["alert_id"])
    if alert is None:
        raise HTTPException(
            status_code=404,
            detail=f"Alert {inv['alert_id']} not found in Wazuh Indexer",
        )

    background_tasks.add_task(investigator.investigate, investigation_id, alert)
    return {"status": "started", "investigation_id": investigation_id}

# ─────────────────────────────────────────────────────────────────────────────
# Routes - Evidence
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{investigation_id}/evidence")
def list_evidence(investigation_id: str, db: Database = Depends(get_db)):
    _ensure_investigation_exists(db, investigation_id)
    return db.fetchall(
        "SELECT * FROM investigation_evidence WHERE investigation_id = %s ORDER BY created_at DESC", 
        (investigation_id,)
    )

@router.post("/{investigation_id}/evidence", status_code=201)
def add_evidence(
    investigation_id: str, 
    evidence: EvidenceCreate, 
    db: Database = Depends(get_db)
):
    _ensure_investigation_exists(db, investigation_id)
    evidence_id = new_id()
    data_json = json.dumps(evidence.data) if evidence.data else None
    
    query = """
        INSERT INTO investigation_evidence 
        (id, investigation_id, source_type, source_id, data, notes, collected_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
    """
    params = (
        evidence_id, 
        investigation_id, 
        evidence.source_type, 
        evidence.source_id, 
        data_json, 
        evidence.notes, 
        evidence.collected_by
    )
    db.execute(query, params)
    return db.fetchone("SELECT * FROM investigation_evidence WHERE id = %s", (evidence_id,))

# ─────────────────────────────────────────────────────────────────────────────
# Routes - Analysis
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{investigation_id}/analysis")
def list_analysis(investigation_id: str, db: Database = Depends(get_db)):
    _ensure_investigation_exists(db, investigation_id)
    return db.fetchall(
        "SELECT * FROM investigation_analysis WHERE investigation_id = %s ORDER BY created_at DESC", 
        (investigation_id,)
    )

@router.post("/{investigation_id}/analysis", status_code=201)
def add_analysis(
    investigation_id: str, 
    analysis: AnalysisCreate, 
    db: Database = Depends(get_db)
):
    _ensure_investigation_exists(db, investigation_id)
    analysis_id = new_id()
    
    query = """
        INSERT INTO investigation_analysis
        (id, investigation_id, analysis_type, verdict, content, confidence, model_id, created_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
    """
    params = (
        analysis_id,
        investigation_id,
        analysis.analysis_type,
        analysis.verdict,
        analysis.content,
        analysis.confidence,
        analysis.model_id,
        analysis.created_by
    )
    db.execute(query, params)
    return db.fetchone("SELECT * FROM investigation_analysis WHERE id = %s", (analysis_id,))

# ─────────────────────────────────────────────────────────────────────────────
# Routes - Actions
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{investigation_id}/actions")
def list_actions(investigation_id: str, db: Database = Depends(get_db)):
    _ensure_investigation_exists(db, investigation_id)
    return db.fetchall(
        "SELECT * FROM investigation_actions WHERE investigation_id = %s ORDER BY created_at DESC", 
        (investigation_id,)
    )

@router.post("/{investigation_id}/actions", status_code=201)
def add_action(
    investigation_id: str, 
    action: ActionCreate, 
    db: Database = Depends(get_db)
):
    _ensure_investigation_exists(db, investigation_id)
    action_id = new_id()
    
    query = """
        INSERT INTO investigation_actions
        (id, investigation_id, action_type, description, reasoning, status, performed_by, created_at)
        VALUES (%s, %s, %s, %s, %s, 'pending', %s, NOW())
    """
    params = (
        action_id,
        investigation_id,
        action.action_type,
        action.description,
        action.reasoning,
        action.performed_by
    )
    db.execute(query, params)
    return db.fetchone("SELECT * FROM investigation_actions WHERE id = %s", (action_id,))

@router.patch("/{investigation_id}/actions/{action_id}")
def update_action(
    investigation_id: str, 
    action_id: str,
    update_data: ActionUpdate, 
    db: Database = Depends(get_db)
):
    _ensure_investigation_exists(db, investigation_id)
    
    # Ensure action exists and belongs to investigation
    row = db.fetchone(
        "SELECT id FROM investigation_actions WHERE id = %s AND investigation_id = %s", 
        (action_id, investigation_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
        
    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
        return db.fetchone("SELECT * FROM investigation_actions WHERE id = %s", (action_id,))
        
    set_clauses = []
    params = []
    for key, value in update_dict.items():
        set_clauses.append(f"{key} = %s")
        params.append(value)
        
    if "status" in update_dict and update_dict["status"] in ("completed", "failed"):
        set_clauses.append("completed_at = NOW()")
        
    query = f"UPDATE investigation_actions SET {', '.join(set_clauses)} WHERE id = %s AND investigation_id = %s"
    params.extend([action_id, investigation_id])
    
    db.execute(query, tuple(params))
    return db.fetchone("SELECT * FROM investigation_actions WHERE id = %s", (action_id,))
