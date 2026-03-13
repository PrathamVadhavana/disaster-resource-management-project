"""
AI Victim Chatbot Service — Phase 3
Multi-step conversational intake assistant that guides victims through
structured resource request creation using rule-based NLP.

Zero external API dependencies — fully self-contained state-machine
conversation engine.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.nlp_service import (
    classify_request,
    classify_resource_type,
    estimate_quantity,
    extract_urgency_signals,
)
from app.services.distance import haversine

logger = logging.getLogger(__name__)

# ── Database client (lazy import to avoid initialization issues) ────────────────────
def _get_db():
    """Get database client, avoiding circular imports."""
    from app.database import db_admin
    return db_admin


# ── Conversation states ────────────────────────────────────────────────────────
class ConvState(StrEnum):
    GREETING = "greeting"
    ASK_SITUATION = "ask_situation"
    ASK_RESOURCE = "ask_resource"
    ASK_QUANTITY = "ask_quantity"
    ASK_LOCATION = "ask_location"
    ASK_PEOPLE = "ask_people"
    ASK_MEDICAL = "ask_medical"
    CONFIRM = "confirm"
    SUBMITTED = "submitted"


# ── Data models ────────────────────────────────────────────────────────────────
@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict | None = None


@dataclass
class ExtractedData:
    """Progressively built request data from conversation."""

    situation_description: str = ""
    resource_types: list[str] = field(default_factory=list)
    resource_type_scores: dict[str, float] = field(default_factory=dict)
    quantity: int = 1
    location: str = ""
    people_count: int = 1
    has_medical_needs: bool = False
    medical_details: str = ""
    disaster_type: str | None = None
    urgency_signals: list[dict] = field(default_factory=list)
    recommended_priority: str = "medium"
    priority_escalated: bool = False
    confidence: float = 0.5
    raw_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "situation_description": self.situation_description,
            "resource_types": self.resource_types,
            "resource_type_scores": self.resource_type_scores,
            "quantity": self.quantity,
            "location": self.location,
            "people_count": self.people_count,
            "has_medical_needs": self.has_medical_needs,
            "medical_details": self.medical_details,
            "disaster_type": self.disaster_type,
            "urgency_signals": self.urgency_signals,
            "recommended_priority": self.recommended_priority,
            "priority_escalated": self.priority_escalated,
            "confidence": self.confidence,
        }


@dataclass
class ChatSession:
    session_id: str
    state: ConvState = ConvState.GREETING
    messages: list[ChatMessage] = field(default_factory=list)
    extracted: ExtractedData = field(default_factory=ExtractedData)
    states_visited: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── In-memory session store ────────────────────────────────────────────────────
_sessions: dict[str, ChatSession] = {}


def get_or_create_session(session_id: str | None = None) -> ChatSession:
    """Return an existing session or create a new one."""
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    new_id = session_id or str(uuid.uuid4())
    session = ChatSession(session_id=new_id)
    _sessions[new_id] = session
    return session


def delete_session(session_id: str) -> bool:
    """Remove a session from the store."""
    return _sessions.pop(session_id, None) is not None


def get_session_data(session_id: str) -> dict | None:
    """Return extracted data for a session, or None if not found."""
    session = _sessions.get(session_id)
    if not session:
        return None
    return session.extracted.to_dict()


# ── Response templates ─────────────────────────────────────────────────────────
GREETING_MSG = (
    "Hello! I'm here to help you request emergency resources. "
    "I'll guide you through a few quick questions so we can get help to you as fast as possible.\n\n"
    "**Can you describe your current situation?** "
    "For example: what happened, what do you need most urgently?"
)

RESOURCE_CONFIRM_TEMPLATE = (
    "Based on what you've told me, it sounds like you need: **{types}**.\n\n"
    "Is that correct? If you need something different or additional, just let me know. "
    "Otherwise, say **yes** to continue."
)

RESOURCE_ASK = (
    "I wasn't able to determine the type of resource you need. "
    "Could you tell me what you need most? For example:\n"
    "- Food\n- Water\n- Medical supplies\n- Shelter\n- Clothing\n- Evacuation\n- Volunteers\n- Financial aid"
)

QUANTITY_ASK_TEMPLATE = (
    "How many **{resource}** units/items do you need? And for how many people? (e.g., '5 water bottles for 3 people')"
)

LOCATION_ASK = (
    "Where are you located? Please provide as much detail as possible — "
    "address, neighborhood, landmark, or GPS coordinates if you have them."
)

PEOPLE_ASK = (
    "How many people are with you who need help? "
    "Are there any children, elderly, or people with disabilities in your group?"
)

MEDICAL_ASK = (
    "Does anyone in your group have medical needs or injuries that require attention? If yes, please describe briefly."
)

CONFIRM_TEMPLATE = (
    "Here's a summary of your request:\n\n"
    "📋 **Situation:** {situation}\n"
    "📦 **Resource needed:** {resource}\n"
    "🔢 **Quantity:** {quantity}\n"
    "👥 **People:** {people}\n"
    "📍 **Location:** {location}\n"
    "🏥 **Medical needs:** {medical}\n"
    "⚡ **Priority:** {priority}\n\n"
    "Does this look correct? Say **yes** to submit or **no** to start over."
)

SUBMITTED_MSG = (
    "Your request has been submitted successfully! "
    "A team member will review it shortly. "
    "Your reference information has been saved.\n\n"
    "If your situation changes, you can start a new conversation. Stay safe!"
)


# ── Conversation engine ───────────────────────────────────────────────────────


def _detect_yes(text: str) -> bool:
    """Check if user is affirming."""
    text_lower = text.strip().lower()
    return bool(
        re.match(
            r"^(yes|yeah|yep|yup|correct|sure|ok|okay|y|confirm|right|that'?s? (right|correct))[\.\!\s]*$", text_lower
        )
    )


def _detect_no(text: str) -> bool:
    """Check if user is negating."""
    text_lower = text.strip().lower()
    return bool(re.match(r"^(no|nah|nope|wrong|incorrect|n|not really|start over|reset)[\.\!\s]*$", text_lower))


def _extract_number(text: str) -> int | None:
    """Pull the first integer from text."""
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return int(match.group(1))
    return None


def _detect_medical(text: str) -> bool:
    """Check if text mentions medical needs."""
    medical_kw = (
        r"\b(injur|wound|bleed|fracture|medic|sick|fever|pain|diabet|asthma|chronic|surgery|pregnant|disability)\b"
    )
    return bool(re.search(medical_kw, text.lower()))


def process_message(session_id: str | None, user_message: str) -> dict:
    """
    Process one user message in the conversation.
    Returns the chatbot response with metadata.
    """
    session = get_or_create_session(session_id)
    session.updated_at = datetime.now(UTC).isoformat()

    # Store user message
    session.messages.append(ChatMessage(role="user", content=user_message))
    session.extracted.raw_messages.append(user_message)

    # Run through the state machine
    response_text, metadata = _handle_state(session, user_message)

    # Store assistant message
    session.messages.append(ChatMessage(role="assistant", content=response_text, metadata=metadata))

    return {
        "session_id": session.session_id,
        "message": response_text,
        "state": session.state.value,
        "extracted_data": session.extracted.to_dict(),
        "metadata": metadata,
    }


def _handle_state(session: ChatSession, user_input: str) -> tuple[str, dict]:
    """Route user input through the conversation state machine."""

    # Track state transitions
    current_state = session.state.value
    if current_state not in session.states_visited:
        session.states_visited.append(current_state)

    # ── GREETING: first interaction ──
    if session.state == ConvState.GREETING:
        session.state = ConvState.ASK_SITUATION
        return GREETING_MSG, {"next_state": "ask_situation"}

    # ── ASK_SITUATION: user describes their situation ──
    elif session.state == ConvState.ASK_SITUATION:
        return _handle_situation(session, user_input)

    # ── ASK_RESOURCE: confirm or correct detected resource type ──
    elif session.state == ConvState.ASK_RESOURCE:
        return _handle_resource(session, user_input)

    # ── ASK_QUANTITY: how much / how many ──
    elif session.state == ConvState.ASK_QUANTITY:
        return _handle_quantity(session, user_input)

    # ── ASK_LOCATION: where are they ──
    elif session.state == ConvState.ASK_LOCATION:
        return _handle_location(session, user_input)

    # ── ASK_PEOPLE: group size & vulnerabilities ──
    elif session.state == ConvState.ASK_PEOPLE:
        return _handle_people(session, user_input)

    # ── ASK_MEDICAL: medical needs ──
    elif session.state == ConvState.ASK_MEDICAL:
        return _handle_medical(session, user_input)

    # ── CONFIRM: review and submit ──
    elif session.state == ConvState.CONFIRM:
        return _handle_confirm(session, user_input)

    # ── SUBMITTED: already done ──
    elif session.state == ConvState.SUBMITTED:
        return (
            "Your request has already been submitted. Start a new conversation if you need additional help.",
            {"already_submitted": True},
        )

    return "I'm sorry, something went wrong. Please try again.", {}


def _handle_situation(session: ChatSession, text: str) -> tuple[str, dict]:
    """Process the user's situation description."""
    session.extracted.situation_description = text

    # Run NLP pipeline on the full description
    full_text = " ".join(session.extracted.raw_messages)
    classification = classify_request(full_text)

    # Store results
    session.extracted.urgency_signals = classification.urgency_signals
    session.extracted.recommended_priority = classification.recommended_priority
    session.extracted.priority_escalated = classification.priority_was_escalated
    session.extracted.confidence = classification.confidence
    session.extracted.resource_types = classification.resource_types
    session.extracted.resource_type_scores = classification.resource_type_scores
    session.extracted.disaster_type = classification.disaster_type

    # Try to detect quantity from situation text
    qty = estimate_quantity(text)
    if qty > 1:
        session.extracted.quantity = qty

    metadata = {
        "classification": classification.to_dict(),
    }

    # If resource detected with decent confidence, confirm it
    if classification.resource_types and classification.resource_types != ["Custom"]:
        types_str = ", ".join(classification.resource_types[:3])
        session.state = ConvState.ASK_RESOURCE
        return RESOURCE_CONFIRM_TEMPLATE.format(types=types_str), metadata
    else:
        # Couldn't detect — ask directly
        session.state = ConvState.ASK_RESOURCE
        return RESOURCE_ASK, metadata


def _handle_resource(session: ChatSession, text: str) -> tuple[str, dict]:
    """Handle resource type confirmation or correction."""
    if _detect_yes(text) and session.extracted.resource_types:
        # Confirmed — move to quantity
        primary = session.extracted.resource_types[0]
        session.state = ConvState.ASK_QUANTITY
        return QUANTITY_ASK_TEMPLATE.format(resource=primary), {}

    # User provided a correction or new resource type
    types, scores = classify_resource_type(text)
    if types and types != ["Custom"]:
        session.extracted.resource_types = types
        session.extracted.resource_type_scores = scores
        primary = types[0]
        session.state = ConvState.ASK_QUANTITY
        return (
            f"Got it — I've updated your request to **{', '.join(types[:3])}**.\n\n"
            + QUANTITY_ASK_TEMPLATE.format(resource=primary)
        ), {"updated_types": types}

    # Still couldn't detect — try mapping free text directly
    text_lower = text.strip().lower()
    direct_map = {
        "food": "Food",
        "water": "Water",
        "medical": "Medical",
        "shelter": "Shelter",
        "clothing": "Clothing",
        "clothes": "Clothing",
        "evacuation": "Evacuation",
        "volunteers": "Volunteers",
        "financial": "Financial Aid",
        "money": "Financial Aid",
    }
    for key, rtype in direct_map.items():
        if key in text_lower:
            session.extracted.resource_types = [rtype]
            session.extracted.resource_type_scores = {rtype: 0.8}
            session.state = ConvState.ASK_QUANTITY
            return (f"Got it — **{rtype}**.\n\n" + QUANTITY_ASK_TEMPLATE.format(resource=rtype)), {
                "updated_types": [rtype]
            }

    # Still can't determine
    return (
        "I'm not sure what resource type that is. Could you pick one from this list?\n\n"
        "- Food\n- Water\n- Medical\n- Shelter\n- Clothing\n- Evacuation\n- Volunteers\n- Financial Aid"
    ), {"retry": True}


def _handle_quantity(session: ChatSession, text: str) -> tuple[str, dict]:
    """Extract quantity from user response."""
    qty = _extract_number(text)
    if qty:
        session.extracted.quantity = min(qty, 9999)

    # Also check for people count in this answer
    people_match = re.search(r"(\d+)\s*(people|persons?|family members?|of us)", text.lower())
    if people_match:
        session.extracted.people_count = int(people_match.group(1))

    session.state = ConvState.ASK_LOCATION
    return LOCATION_ASK, {"quantity_detected": session.extracted.quantity}


def _handle_location(session: ChatSession, text: str) -> tuple[str, dict]:
    """Store location information."""
    session.extracted.location = text.strip()
    session.state = ConvState.ASK_PEOPLE
    return PEOPLE_ASK, {}


def _handle_people(session: ChatSession, text: str) -> tuple[str, dict]:
    """Extract people count and vulnerabilities."""
    qty = _extract_number(text)
    if qty:
        session.extracted.people_count = qty

    # Check for vulnerabilities (may trigger priority escalation)
    signals = extract_urgency_signals(text)
    if signals:
        new_signals = [{"keyword": s.keyword, "label": s.label, "severity_boost": s.severity_boost} for s in signals]
        session.extracted.urgency_signals.extend(new_signals)
        # Re-escalate priority
        from app.services.nlp_service import UrgencySignal as US
        from app.services.nlp_service import escalate_priority

        signal_objects = [
            US(keyword=s["keyword"], label=s["label"], severity_boost=s["severity_boost"], offset=0)
            for s in session.extracted.urgency_signals
        ]
        new_pri, escalated = escalate_priority("medium", signal_objects)
        session.extracted.recommended_priority = new_pri
        session.extracted.priority_escalated = escalated

    # Check if medical info was already mentioned
    if _detect_medical(text):
        session.extracted.has_medical_needs = True
        session.extracted.medical_details = text
        session.state = ConvState.CONFIRM
        return _build_confirmation(session), {"skipped_medical_ask": True}

    session.state = ConvState.ASK_MEDICAL
    return MEDICAL_ASK, {}


def _handle_medical(session: ChatSession, text: str) -> tuple[str, dict]:
    """Process medical needs response."""
    if _detect_no(text):
        session.extracted.has_medical_needs = False
    else:
        session.extracted.has_medical_needs = True
        session.extracted.medical_details = text

        # Check for urgency signals in medical details
        signals = extract_urgency_signals(text)
        if signals:
            new_signals = [
                {"keyword": s.keyword, "label": s.label, "severity_boost": s.severity_boost} for s in signals
            ]
            session.extracted.urgency_signals.extend(new_signals)
            from app.services.nlp_service import UrgencySignal as US
            from app.services.nlp_service import escalate_priority

            signal_objects = [
                US(keyword=s["keyword"], label=s["label"], severity_boost=s["severity_boost"], offset=0)
                for s in session.extracted.urgency_signals
            ]
            new_pri, escalated = escalate_priority("medium", signal_objects)
            session.extracted.recommended_priority = new_pri
            session.extracted.priority_escalated = escalated

    session.state = ConvState.CONFIRM
    return _build_confirmation(session), {}


def _build_confirmation(session: ChatSession) -> str:
    """Build the confirmation summary message."""
    d = session.extracted
    resource_str = ", ".join(d.resource_types) if d.resource_types else "Not determined"
    medical_str = d.medical_details if d.has_medical_needs else "None reported"
    priority_str = d.recommended_priority.upper()
    if d.priority_escalated:
        priority_str += " (auto-escalated due to urgency signals)"

    return CONFIRM_TEMPLATE.format(
        situation=d.situation_description[:200] or "Not provided",
        resource=resource_str,
        quantity=d.quantity,
        people=d.people_count,
        location=d.location or "Not provided",
        medical=medical_str,
        priority=priority_str,
    )


def _handle_confirm(session: ChatSession, text: str) -> tuple[str, dict]:
    """Handle confirmation response."""
    if _detect_yes(text):
        session.state = ConvState.SUBMITTED
        # Track final state
        if ConvState.CONFIRM.value not in session.states_visited:
            session.states_visited.append(ConvState.CONFIRM.value)
        if ConvState.SUBMITTED.value not in session.states_visited:
            session.states_visited.append(ConvState.SUBMITTED.value)

        # Log the completed session
        from functools import partial

        # Extract data for logging
        final_resource = session.extracted.resource_types[0] if session.extracted.resource_types else None
        final_priority = session.extracted.recommended_priority

        # Run async logging in sync context using asyncio.run (or fire-and-forget)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a task
                asyncio.create_task(
                    log_chatbot_session(
                        session_id=session.session_id,
                        user_id=None,  # Will be set when user authentication is integrated
                        states_visited=session.states_visited,
                        final_resource_type=final_resource,
                        final_priority=final_priority,
                        completion_status="completed"
                    )
                )
            else:
                loop.run_until_complete(
                    log_chatbot_session(
                        session_id=session.session_id,
                        user_id=None,
                        states_visited=session.states_visited,
                        final_resource_type=final_resource,
                        final_priority=final_priority,
                        completion_status="completed"
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to log completed session: {e}")

        return SUBMITTED_MSG, {
            "submitted": True,
            "extracted_data": session.extracted.to_dict(),
        }
    elif _detect_no(text):
        # Reset to start - log as abandoned
        # Track the confirm state before resetting
        if ConvState.CONFIRM.value not in session.states_visited:
            session.states_visited.append(ConvState.CONFIRM.value)

        # Log abandoned session
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    log_chatbot_session(
                        session_id=session.session_id,
                        user_id=None,
                        states_visited=session.states_visited,
                        final_resource_type=None,
                        final_priority=None,
                        completion_status="abandoned"
                    )
                )
            else:
                loop.run_until_complete(
                    log_chatbot_session(
                        session_id=session.session_id,
                        user_id=None,
                        states_visited=session.states_visited,
                        final_resource_type=None,
                        final_priority=None,
                        completion_status="abandoned"
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to log abandoned session: {e}")

        session.state = ConvState.ASK_SITUATION
        session.extracted = ExtractedData()
        return (
            "No problem! Let's start over.\n\n"
            "**Can you describe your current situation?** "
            "What happened and what do you need?"
        ), {"reset": True}
    else:
        return ("Please confirm by saying **yes** to submit your request, or **no** to start over."), {
            "awaiting_confirmation": True
        }


# ── Smart Defaults & Urgency Context Services ─────────────────────────────────────


@dataclass
class SmartDefaultsResult:
    """Result of get_smart_defaults query."""
    top_resource_types: list[str]
    area_message: str
    has_data: bool


@dataclass
class UrgencyContextResult:
    """Result of get_urgency_context check."""
    has_active_disaster: bool
    disaster_type: str | None
    disaster_title: str | None
    priority_boost: int
    urgency_message: str | None


async def get_smart_defaults(user_location: tuple[float, float]) -> SmartDefaultsResult:
    """
    Query resource_requests from the last 30 days where latitude/longitude
    is within 50km of user_location. Return the top 3 most requested types.

    Args:
        user_location: Tuple of (latitude, longitude)

    Returns:
        SmartDefaultsResult with top resource types and a message for the user
    """
    from datetime import timedelta

    user_lat, user_lon = user_location
    thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    try:
        db = _get_db()
        # Fetch resource requests from last 30 days with location data
        response = await db.table("resource_requests").select(
            "id, resource_type, latitude, longitude, created_at"
        ).gte("created_at", thirty_days_ago).execute()

        requests = response.data or []
        if not requests:
            return SmartDefaultsResult(
                top_resource_types=[],
                area_message="",
                has_data=False
            )

        # Count resource types within 50km
        type_counts: dict[str, int] = {}
        for req in requests:
            req_lat = req.get("latitude")
            req_lon = req.get("longitude")
            if req_lat is None or req_lon is None:
                continue

            distance = haversine(user_lat, user_lon, req_lat, req_lon)
            if distance <= 50:  # Within 50km
                resource_type = req.get("resource_type", "unknown")
                if resource_type:
                    type_counts[resource_type] = type_counts.get(resource_type, 0) + 1

        if not type_counts:
            return SmartDefaultsResult(
                top_resource_types=[],
                area_message="",
                has_data=False
            )

        # Get top 3 most requested types
        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        top_3 = [t[0] for t in sorted_types[:3]]

        # Build user-friendly message
        if top_3:
            if len(top_3) == 1:
                area_message = f"In your area, most people are requesting {top_3[0]}. Is that what you need too?"
            elif len(top_3) == 2:
                area_message = f"In your area, most people are requesting {top_3[0]} and {top_3[1]}. Is either of these what you need?"
            else:
                area_message = f"In your area, most people are requesting {top_3[0]}, {top_3[1]}, or {top_3[2]}. Is any of these what you need?"
        else:
            area_message = ""

        return SmartDefaultsResult(
            top_resource_types=top_3,
            area_message=area_message,
            has_data=True
        )

    except Exception as e:
        logger.warning(f"Error getting smart defaults: {e}")
        return SmartDefaultsResult(
            top_resource_types=[],
            area_message="",
            has_data=False
        )


async def get_urgency_context(user_location: tuple[float, float]) -> UrgencyContextResult:
    """
    Check for any active (status='active') disaster within 100km of user_location.
    If found, auto-boost priority by 1 level and inform the user.

    Args:
        user_location: Tuple of (latitude, longitude)

    Returns:
        UrgencyContextResult with disaster info and priority boost
    """
    user_lat, user_lon = user_location

    try:
        db = _get_db()
        # Fetch active disasters
        response = await db.table("disasters").select(
            "id, type, title, status, location_id"
        ).eq("status", "active").execute()

        disasters = response.data or []
        if not disasters:
            return UrgencyContextResult(
                has_active_disaster=False,
                disaster_type=None,
                disaster_title=None,
                priority_boost=0,
                urgency_message=None
            )

        # Need to get location data for each disaster to calculate distance
        location_ids = [d.get("location_id") for d in disasters if d.get("location_id")]
        location_map = {}

        if location_ids:
            loc_response = await db.table("locations").select(
                "id, latitude, longitude"
            ).in_("id", location_ids).execute()
            for loc in loc_response.data or []:
                location_map[loc["id"]] = loc

        # Check each disaster within 100km
        for disaster in disasters:
            location_id = disaster.get("location_id")
            if not location_id or location_id not in location_map:
                continue

            loc = location_map[location_id]
            disaster_lat = loc.get("latitude")
            disaster_lon = loc.get("longitude")

            if disaster_lat is None or disaster_lon is None:
                continue

            distance = haversine(user_lat, user_lon, disaster_lat, disaster_lon)

            if distance <= 100:  # Within 100km
                disaster_type = disaster.get("type", "disaster")
                disaster_title = disaster.get("title", "")

                return UrgencyContextResult(
                    has_active_disaster=True,
                    disaster_type=disaster_type,
                    disaster_title=disaster_title,
                    priority_boost=1,
                    urgency_message=f"There's an active {disaster_type} near you. We've marked your request as high priority."
                )

        return UrgencyContextResult(
            has_active_disaster=False,
            disaster_type=None,
            disaster_title=None,
            priority_boost=0,
            urgency_message=None
        )

    except Exception as e:
        logger.warning(f"Error getting urgency context: {e}")
        return UrgencyContextResult(
            has_active_disaster=False,
            disaster_type=None,
            disaster_title=None,
            priority_boost=0,
            urgency_message=None
        )


async def log_chatbot_session(
    session_id: str,
    user_id: str | None,
    states_visited: list[str],
    final_resource_type: str | None,
    final_priority: str | None,
    completion_status: str
) -> bool:
    """
    Log a completed chatbot session to the chatbot_sessions table.

    Args:
        session_id: The unique session identifier
        user_id: The user ID if authenticated
        states_visited: List of conversation states visited
        final_resource_type: The resource type selected
        final_priority: The priority of the request
        completion_status: 'completed' or 'abandoned'

    Returns:
        True if logged successfully, False otherwise
    """
    try:
        db = _get_db()
        insert_data = {
            "session_id": session_id,
            "user_id": user_id,
            "states_visited": states_visited,
            "final_resource_type": final_resource_type,
            "final_priority": final_priority,
            "completion_status": completion_status,
        }

        await db.table("chatbot_sessions").insert(insert_data).execute()
        logger.info(f"Logged chatbot session {session_id} as {completion_status}")
        return True

    except Exception as e:
        logger.error(f"Error logging chatbot session {session_id}: {e}")
        return False
