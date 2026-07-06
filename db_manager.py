import os
import logging
import mcp_server_db
import contextvars

logger = logging.getLogger("db_manager")

# Request-scoped ContextVar to collect MCP logs for API responses
mcp_logs_var = contextvars.ContextVar("mcp_logs_var", default=None)


def log_mcp_traffic(direction: str, payload: dict):
    """
    Log MCP JSON-RPC messages into the request context (FastAPI) or Streamlit session state.
    """
    # 1. Log to context variable if active
    current_logs = mcp_logs_var.get()
    if current_logs is not None:
        current_logs.append({
            "direction": direction,
            "payload": payload
        })


def init_db() -> bool:
    """
    Delegates initialization to the MCP Server.
    """
    return mcp_server_db.init_firestore()

def get_events() -> list:
    """
    Fetches events collection through Firestore MCP query_collection tool.
    """
    try:
        events = mcp_server_db.call_tool_client_side(
            "query_collection", 
            {"collection_name": "events"},
            console_log_callback=log_mcp_traffic
        )
        return events
    except Exception as e:
        logger.error(f"MCP Client Error: {e}")
        return []

def add_event(title: str, date: str, desc: str) -> dict:
    """
    Inserts event document through Firestore MCP insert_document tool.
    """
    import uuid
    doc_id = str(uuid.uuid4())[:8] if not date else f"{title.lower().replace(' ', '-')}-{date.lower().replace(' ', '-')}"
    # Remove special characters from doc_id for safety
    doc_id = "".join(c for c in doc_id if c.isalnum() or c == "-")
    
    event_data = {
        "id": doc_id,
        "title": f"{title} ({date})" if date else title,
        "date": date,
        "description": desc
    }
    
    mcp_server_db.call_tool_client_side(
        "insert_document",
        {
            "collection_name": "events",
            "doc_id": doc_id,
            "document_data": event_data
        },
        console_log_callback=log_mcp_traffic
    )
    return event_data

def get_blogs() -> list:
    """
    Queries blogs collection through Firestore MCP query_collection tool.
    """
    try:
        blogs = mcp_server_db.call_tool_client_side(
            "query_collection",
            {"collection_name": "blogs"},
            console_log_callback=log_mcp_traffic
        )
        return blogs
    except Exception as e:
        logger.error(f"MCP Client Error: {e}")
        return []

def add_blog(title: str, author: str, date: str, content: str) -> dict:
    """
    Inserts blog document through Firestore MCP insert_document tool.
    """
    import uuid
    doc_id = f"blog-{str(uuid.uuid4())[:8]}"
    blog_data = {
        "id": doc_id,
        "title": title,
        "author": author,
        "date": date,
        "content": content
    }
    
    mcp_server_db.call_tool_client_side(
        "insert_document",
        {
            "collection_name": "blogs",
            "doc_id": doc_id,
            "document_data": blog_data
        },
        console_log_callback=log_mcp_traffic
    )
    return blog_data

def get_form_schemas() -> dict:
    """
    Queries form schemas through Firestore MCP. Returns as key-value dictionary.
    """
    try:
        schemas_list = mcp_server_db.call_tool_client_side(
            "query_collection",
            {"collection_name": "form_schemas"},
            console_log_callback=log_mcp_traffic
        )
        # Convert list back to dictionary mapping event title -> config
        schemas_dict = {}
        for schema in schemas_list:
            event_id = schema.get("id")
            schemas_dict[event_id] = {
                "active": schema.get("active", True),
                "fee": schema.get("fee", 0.0)
            }
        return schemas_dict
    except Exception as e:
        logger.error(f"MCP Client Error: {e}")
        return {}

def add_form_schema(event_title: str, fee: float) -> dict:
    """
    Creates/updates form schema configuration.
    """
    schema_data = {
        "active": True,
        "fee": float(fee)
    }
    mcp_server_db.call_tool_client_side(
        "insert_document",
        {
            "collection_name": "form_schemas",
            "doc_id": event_title,
            "document_data": schema_data
        },
        console_log_callback=log_mcp_traffic
    )
    return schema_data

def get_registrations() -> list:
    """
    Queries registrations through Firestore MCP.
    """
    try:
        regs = mcp_server_db.call_tool_client_side(
            "query_collection",
            {"collection_name": "registrations"},
            console_log_callback=log_mcp_traffic
        )
        return regs
    except Exception as e:
        logger.error(f"MCP Client Error: {e}")
        return []

def add_registration(data: dict) -> dict:
    """
    Inserts a registration entry through Firestore MCP.
    """
    doc_id = str(data["id"])
    mcp_server_db.call_tool_client_side(
        "insert_document",
        {
            "collection_name": "registrations",
            "doc_id": doc_id,
            "document_data": data
        },
        console_log_callback=log_mcp_traffic
    )
    return data

def update_registration_status(reg_id: int, status: str) -> bool:
    """
    Updates registration status through Firestore MCP update_document.
    """
    try:
        doc_id = str(reg_id)
        mcp_server_db.call_tool_client_side(
            "update_document",
            {
                "collection_name": "registrations",
                "doc_id": doc_id,
                "document_data": {"status": status}
            },
            console_log_callback=log_mcp_traffic
        )
        return True
    except Exception:
        return False

def cleanup_db():
    """
    Resets the database by removing non-Ganeshotsav events/schemas through Firestore MCP.
    """
    try:
        # Query existing events
        events = get_events()
        for e in events:
            if "Ganesh" not in e.get("title", ""):
                mcp_server_db.call_tool_client_side(
                    "delete_document",
                    {"collection_name": "events", "doc_id": e["id"]},
                    console_log_callback=log_mcp_traffic
                )
                
        # Query schemas
        schemas = get_form_schemas()
        for key in schemas.keys():
            if "Ganesh" not in key:
                mcp_server_db.call_tool_client_side(
                    "delete_document",
                    {"collection_name": "form_schemas", "doc_id": key},
                    console_log_callback=log_mcp_traffic
                )
    except Exception as e:
        logger.error(f"MCP Cleanup Error: {e}")
