"""
FastAPI router for the investigations resource.
"""

import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import Database, new_id
from api.dependencies import get_db, get_investigation_manager

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
    content: str
    confidence: Optional[float] = None
    model_id: Optional[str] = None
    created_by: Optional[str] = None

class ActionCreate(BaseModel):
    action_type: str
    description: str
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
        (id, investigation_id, analysis_type, content, confidence, model_id, created_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
    """
    params = (
        analysis_id, 
        investigation_id, 
        analysis.analysis_type, 
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
        (id, investigation_id, action_type, description, status, performed_by, created_at)
        VALUES (%s, %s, %s, %s, 'pending', %s, NOW())
    """
    params = (
        action_id, 
        investigation_id, 
        action.action_type, 
        action.description, 
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
