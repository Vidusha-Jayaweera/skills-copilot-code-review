"""
Endpoints to manage announcements.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime
from bson.objectid import ObjectId
from pydantic import BaseModel

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _to_output(doc: dict) -> dict:
    """Convert mongo doc to JSON-serializable dict"""
    return {
        "id": str(doc.get("_id")),
        "message": doc.get("message"),
        "start_date": doc.get("start_date"),
        "expiration_date": doc.get("expiration_date"),
        "created_at": doc.get("created_at"),
    }


@router.get("", response_model=List[Dict[str, Any]])
def list_announcements() -> List[Dict[str, Any]]:
    """List all announcements (management view)"""
    anns = []
    for a in announcements_collection.find().sort("created_at", -1):
        anns.append(_to_output(a))
    return anns


@router.get("/active", response_model=List[Dict[str, Any]])
def list_active_announcements() -> List[Dict[str, Any]]:
    """Return announcements that are currently active (start <= now < expiration)"""
    now = datetime.utcnow().isoformat()
    anns = []
    for a in announcements_collection.find():
        start = a.get("start_date")
        exp = a.get("expiration_date")
        # If expiration missing, skip
        if not exp:
            continue
        if start and start > now:
            # not started
            continue
        if exp <= now:
            # expired
            continue
        anns.append(_to_output(a))
    # sort by created_at
    anns.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return anns


@router.post("", response_model=Dict[str, Any])
class AnnouncementIn(BaseModel):
    message: str
    expiration_date: str
    start_date: Optional[str] = None


def _ensure_teacher(teacher_username: Optional[str]):
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")
    return teacher


def create_announcement(payload: AnnouncementIn, teacher_username: Optional[str] = None):
    """Create an announcement. Requires teacher_username for auth."""
    _ensure_teacher(teacher_username)
    now = datetime.utcnow().isoformat()
    doc = {
        "message": payload.message,
        "start_date": payload.start_date,
        "expiration_date": payload.expiration_date,
        "created_at": now,
    }
    result = announcements_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_output(doc)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
class AnnouncementUpdate(BaseModel):
    message: Optional[str] = None
    start_date: Optional[str] = None
    expiration_date: Optional[str] = None


def update_announcement(announcement_id: str, payload: AnnouncementUpdate, teacher_username: Optional[str] = None):
    """Update an announcement. Requires teacher_username for auth."""
    _ensure_teacher(teacher_username)

    try:
        oid = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement id")

    update = {}
    if payload.message is not None:
        update["message"] = payload.message
    if payload.start_date is not None:
        update["start_date"] = payload.start_date
    if payload.expiration_date is not None:
        update["expiration_date"] = payload.expiration_date

    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = announcements_collection.update_one({"_id": oid}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    ann = announcements_collection.find_one({"_id": oid})
    return _to_output(ann)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = None):
    """Delete an announcement. Requires teacher_username for auth."""
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    try:
        oid = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement id")

    result = announcements_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
