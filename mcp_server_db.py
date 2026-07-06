import os
import json
import logging
from typing import Dict, Any, List
from google.cloud import firestore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GCPFirestoreMCPServer")

# Global variables for Database client and Offline State
_db = None
_is_offline = True

# Local JSON fallback paths (same as original db_manager)
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
EVENTS_FILE = os.path.join(DATA_DIR, "events_db.json")
BLOGS_FILE = os.path.join(DATA_DIR, "blogs_db.json")
SCHEMAS_FILE = os.path.join(DATA_DIR, "schemas_db.json")
REGS_FILE = os.path.join(DATA_DIR, "regs_db.json")

# Default values
DEFAULT_EVENTS = [
    {
        "id": "ganesh-utsav-2026",
        "title": "Ganesh Utsav Cultural Planning (August 2026)",
        "date": "August 2026",
        "description": "Initial meeting to coordinate decorations, cultural performances, and volunteer roles for the upcoming grand celebration."
    }
]

DEFAULT_BLOGS = [
    {
        "id": "our-journey",
        "title": "Our Journey & Evolution",
        "author": "NORWEMA Archive",
        "date": "July 2026",
        "content": "Our long-standing presence began in 1973 with foundations laid in Manchester by the Ganpule family. Over the decades, we have grown from a tight-knit doctor community initiative into a unifying regional association. Today, we are proud to launch our modern digital home at norwema.org.uk to connect and support Maharashtrian families across the North West."
    }
]

DEFAULT_SCHEMAS = {
    "Ganesh Utsav Cultural Planning (August 2026)": {"active": True, "fee": 25.0}
}

def init_firestore() -> bool:
    """
    Initializes Firestore client if credentials exist, otherwise sets _is_offline = True.
    """
    global _db, _is_offline
    if _db is not None:
        return _is_offline
        
    try:
        # Check environment or default credentials
        _db = firestore.Client()
        # Ping connection
        list(_db.collections())
        _is_offline = False
        logger.info("MCP Server: Successfully connected to GCP Firestore.")
    except Exception as e:
        _is_offline = True
        _db = None
        logger.warning(f"MCP Server: Running in Offline Mode (persisting to local JSON). Reason: {e}")
        
    return _is_offline


def reset_firestore_db() -> bool:
    """
    Wipes all documents in events, blogs, form_schemas, and registrations collections,
    then re-seeds events, blogs, and form_schemas with default data.
    Only operates when connected to live Firestore. Returns True on success.
    """
    global _db, _is_offline
    if _is_offline or _db is None:
        logger.warning("MCP Server: reset_firestore_db() skipped — running in offline mode.")
        return False

    try:
        COLLECTIONS = ["events", "blogs", "form_schemas", "registrations"]
        for col_name in COLLECTIONS:
            col_ref = _db.collection(col_name)
            docs = col_ref.stream()
            deleted = 0
            for doc in docs:
                doc.reference.delete()
                deleted += 1
            logger.info(f"MCP Server: Wiped {deleted} docs from '{col_name}'.")

        # Re-seed events
        for event in DEFAULT_EVENTS:
            _db.collection("events").document(event["id"]).set(event)
        logger.info(f"MCP Server: Seeded {len(DEFAULT_EVENTS)} default event(s).")

        # Re-seed blogs
        for blog in DEFAULT_BLOGS:
            _db.collection("blogs").document(blog["id"]).set(blog)
        logger.info(f"MCP Server: Seeded {len(DEFAULT_BLOGS)} default blog(s).")

        # Re-seed form_schemas
        for title, schema in DEFAULT_SCHEMAS.items():
            _db.collection("form_schemas").document(title).set(schema)
        logger.info(f"MCP Server: Seeded {len(DEFAULT_SCHEMAS)} default schema(s).")

        logger.info("MCP Server: Database reset and re-seed complete.")
        return True

    except Exception as e:
        logger.error(f"MCP Server: reset_firestore_db() failed: {e}")
        return False

# JSON Helper Functions
def _read_local_json(file_path: str, default_val) -> Any:
    if not os.path.exists(file_path):
        return default_val
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_val

def _write_local_json(file_path: str, data: Any):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write local JSON {file_path}: {e}")

# MCP TOOL SCHEMAS DEFINITION
MCP_TOOLS = [
    {
        "name": "query_collection",
        "description": "Fetch all documents in a specified Firestore collection ('events', 'blogs', 'registrations', 'form_schemas').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_name": {
                    "type": "string",
                    "enum": ["events", "blogs", "registrations", "form_schemas"],
                    "description": "Name of the database collection to query."
                }
            },
            "required": ["collection_name"]
        }
    },
    {
        "name": "insert_document",
        "description": "Insert or overwrite a document inside a collection with a specific document ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_name": {
                    "type": "string",
                    "enum": ["events", "blogs", "registrations", "form_schemas"],
                    "description": "Target collection."
                },
                "doc_id": {
                    "type": "string",
                    "description": "Unique identifier/document ID for the document."
                },
                "document_data": {
                    "type": "object",
                    "description": "Key-value dictionary containing document fields."
                }
            },
            "required": ["collection_name", "doc_id", "document_data"]
        }
    },
    {
        "name": "update_document",
        "description": "Partially update fields in an existing document inside a collection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_name": {
                    "type": "string",
                    "enum": ["events", "blogs", "registrations", "form_schemas"],
                    "description": "Target collection."
                },
                "doc_id": {
                    "type": "string",
                    "description": "Unique identifier of the document to update."
                },
                "document_data": {
                    "type": "object",
                    "description": "Key-value dictionary of fields to update."
                }
            },
            "required": ["collection_name", "doc_id", "document_data"]
        }
    },
    {
        "name": "delete_document",
        "description": "Remove a document from a collection by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_name": {
                    "type": "string",
                    "enum": ["events", "blogs", "registrations", "form_schemas"],
                    "description": "Target collection."
                },
                "doc_id": {
                    "type": "string",
                    "description": "Document ID to delete."
                }
            },
            "required": ["collection_name", "doc_id"]
        }
    }
]

# REAL FIRESTORE DB IMPLEMENTATION BEHIND MCP
def execute_query_collection(collection_name: str) -> List[Dict[str, Any]]:
    init_firestore()
    if not _is_offline:
        try:
            docs = _db.collection(collection_name).stream()
            results = []
            for doc in docs:
                data = doc.to_dict()
                # Include document ID as field if not present
                if "id" not in data:
                    data["id"] = doc.id
                results.append(data)
            return results
        except Exception as e:
            logger.error(f"Firestore query error: {e}")
            
    # Fallback to local files
    if collection_name == "events":
        return _read_local_json(EVENTS_FILE, DEFAULT_EVENTS)
    elif collection_name == "blogs":
        return _read_local_json(BLOGS_FILE, DEFAULT_BLOGS)
    elif collection_name == "form_schemas":
        schemas = _read_local_json(SCHEMAS_FILE, DEFAULT_SCHEMAS)
        # Format dictionary back into list structure for general query
        return [{"id": k, **v} for k, v in schemas.items()]
    elif collection_name == "registrations":
        return _read_local_json(REGS_FILE, [])
    return []

def execute_insert_document(collection_name: str, doc_id: str, document_data: Dict[str, Any]) -> Dict[str, Any]:
    init_firestore()
    document_data["id"] = doc_id
    if not _is_offline:
        try:
            _db.collection(collection_name).document(doc_id).set(document_data)
            return {"status": "success", "message": f"Document {doc_id} written to GCP Firestore collection {collection_name}."}
        except Exception as e:
            logger.error(f"Firestore insert error: {e}")
            
    # Local fallback
    if collection_name == "events":
        events = _read_local_json(EVENTS_FILE, DEFAULT_EVENTS)
        # Avoid duplicate IDs
        events = [e for e in events if e.get("id") != doc_id]
        events.append(document_data)
        _write_local_json(EVENTS_FILE, events)
    elif collection_name == "blogs":
        blogs = _read_local_json(BLOGS_FILE, DEFAULT_BLOGS)
        blogs = [b for b in blogs if b.get("id") != doc_id]
        blogs.append(document_data)
        _write_local_json(BLOGS_FILE, blogs)
    elif collection_name == "form_schemas":
        schemas = _read_local_json(SCHEMAS_FILE, DEFAULT_SCHEMAS)
        schemas[doc_id] = document_data
        _write_local_json(SCHEMAS_FILE, schemas)
    elif collection_name == "registrations":
        regs = _read_local_json(REGS_FILE, [])
        regs = [r for r in regs if str(r.get("id")) != str(doc_id)]
        regs.append(document_data)
        _write_local_json(REGS_FILE, regs)
        
    return {"status": "success", "message": f"Document {doc_id} written to local database collection {collection_name}."}

def execute_update_document(collection_name: str, doc_id: str, document_data: Dict[str, Any]) -> Dict[str, Any]:
    init_firestore()
    if not _is_offline:
        try:
            _db.collection(collection_name).document(doc_id).update(document_data)
            return {"status": "success", "message": f"Document {doc_id} updated in GCP Firestore collection {collection_name}."}
        except Exception as e:
            logger.error(f"Firestore update error: {e}")
            
    # Local fallback
    if collection_name == "events":
        events = _read_local_json(EVENTS_FILE, DEFAULT_EVENTS)
        for e in events:
            if e.get("id") == doc_id:
                e.update(document_data)
        _write_local_json(EVENTS_FILE, events)
    elif collection_name == "blogs":
        blogs = _read_local_json(BLOGS_FILE, DEFAULT_BLOGS)
        for b in blogs:
            if b.get("id") == doc_id:
                b.update(document_data)
        _write_local_json(BLOGS_FILE, blogs)
    elif collection_name == "form_schemas":
        schemas = _read_local_json(SCHEMAS_FILE, DEFAULT_SCHEMAS)
        if doc_id in schemas:
            schemas[doc_id].update(document_data)
        _write_local_json(SCHEMAS_FILE, schemas)
    elif collection_name == "registrations":
        regs = _read_local_json(REGS_FILE, [])
        for r in regs:
            if str(r.get("id")) == str(doc_id):
                r.update(document_data)
        _write_local_json(REGS_FILE, regs)
        
    return {"status": "success", "message": f"Document {doc_id} updated in local database collection {collection_name}."}

def execute_delete_document(collection_name: str, doc_id: str) -> Dict[str, Any]:
    init_firestore()
    if not _is_offline:
        try:
            _db.collection(collection_name).document(doc_id).delete()
            return {"status": "success", "message": f"Document {doc_id} deleted from GCP Firestore."}
        except Exception as e:
            logger.error(f"Firestore delete error: {e}")
            
    # Local fallback
    if collection_name == "events":
        events = _read_local_json(EVENTS_FILE, DEFAULT_EVENTS)
        events = [e for e in events if e.get("id") != doc_id]
        _write_local_json(EVENTS_FILE, events)
    elif collection_name == "blogs":
        blogs = _read_local_json(BLOGS_FILE, DEFAULT_BLOGS)
        blogs = [b for b in blogs if b.get("id") != doc_id]
        _write_local_json(BLOGS_FILE, blogs)
    elif collection_name == "form_schemas":
        schemas = _read_local_json(SCHEMAS_FILE, DEFAULT_SCHEMAS)
        if doc_id in schemas:
            del schemas[doc_id]
        _write_local_json(SCHEMAS_FILE, schemas)
    elif collection_name == "registrations":
        regs = _read_local_json(REGS_FILE, [])
        regs = [r for r in regs if str(r.get("id")) != str(doc_id)]
        _write_local_json(REGS_FILE, regs)
        
    return {"status": "success", "message": f"Document {doc_id} deleted from local database."}

# MCP JSON-RPC 2.0 HANDLERS
def process_mcp_message(request_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processes an incoming Model Context Protocol JSON-RPC 2.0 message.
    """
    # Validate JSON-RPC
    if request_dict.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Invalid request: missing or invalid jsonrpc version"},
            "id": request_dict.get("id")
        }
        
    msg_id = request_dict.get("id")
    method = request_dict.get("method")
    params = request_dict.get("params", {})
    
    # 1. Handle tools/list method
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": MCP_TOOLS
            },
            "id": msg_id
        }
        
    # 2. Handle tools/call method
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            if tool_name == "query_collection":
                col = arguments.get("collection_name")
                data = execute_query_collection(col)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(data, indent=2)}
                        ]
                    },
                    "id": msg_id
                }
                
            elif tool_name == "insert_document":
                col = arguments.get("collection_name")
                doc_id = arguments.get("doc_id")
                doc_data = arguments.get("document_data")
                res = execute_insert_document(col, doc_id, doc_data)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(res, indent=2)}
                        ]
                    },
                    "id": msg_id
                }
                
            elif tool_name == "update_document":
                col = arguments.get("collection_name")
                doc_id = arguments.get("doc_id")
                doc_data = arguments.get("document_data")
                res = execute_update_document(col, doc_id, doc_data)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(res, indent=2)}
                        ]
                    },
                    "id": msg_id
                }
                
            elif tool_name == "delete_document":
                col = arguments.get("collection_name")
                doc_id = arguments.get("doc_id")
                res = execute_delete_document(col, doc_id)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(res, indent=2)}
                        ]
                    },
                    "id": msg_id
                }
                
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: tool {tool_name} is not registered"},
                    "id": msg_id
                }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Internal error during tool call execution: {e}"},
                "id": msg_id
            }
            
    # 3. Method not found
    else:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method not found: {method}"},
            "id": msg_id
        }

def call_tool_client_side(tool_name: str, arguments: Dict[str, Any], console_log_callback=None) -> Any:
    """
    Helper function acting as the MCP Client. It constructs the JSON-RPC call, 
    records it in the log console, calls the MCP server process, 
    and returns parsed results.
    """
    import random
    request_id = random.randint(1000, 9999)
    
    request_payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": request_id
    }
    
    # Callback to log RPC traffic to UI console
    if console_log_callback:
        console_log_callback("CLIENT_REQUEST", request_payload)
        
    # Execute the RPC call on our local MCP server
    response_payload = process_mcp_message(request_payload)
    
    if console_log_callback:
        console_log_callback("SERVER_RESPONSE", response_payload)
        
    if "error" in response_payload:
        raise Exception(f"MCP Server Error: {response_payload['error']['message']}")
        
    # Extract response content
    text_content = response_payload["result"]["content"][0]["text"]
    return json.loads(text_content)
