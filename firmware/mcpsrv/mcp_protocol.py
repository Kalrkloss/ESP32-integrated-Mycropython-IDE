# Minimaler MCP-Server-Kern (JSON-RPC 2.0) -- MicroPython-tauglich, hostseitig testbar.
# Deckt ab: initialize, notifications/initialized, tools/list, tools/call, ping.
# Bewusst ohne Fremdbibliotheken, damit derselbe Code auf dem ESP32 laeuft.

try:
    import json
except ImportError:  # pragma: no cover
    import ujson as json

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = PROTOCOL_VERSIONS[0]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class Tool:
    """Ein MCP-Tool: Name, Beschreibung, JSON-Schema der Argumente, Handler."""

    def __init__(self, name, description, schema=None, handler=None, title=None):
        self.name = name
        self.title = title
        self.description = description
        self.schema = schema or {"type": "object", "properties": {}, "additionalProperties": False}
        self.handler = handler

    def descriptor(self):
        d = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.schema,
        }
        if self.title:
            d["title"] = self.title
        return d

    def call(self, arguments):
        """Gibt eine MCP-content-Liste zurueck."""
        args = dict(arguments or {})
        result = self.handler(**args) if self.handler else None
        return _to_content(result)


def text_result(text):
    return {"content": [{"type": "text", "text": text}]}


def error_result(text):
    return {"content": [{"type": "text", "text": text}], "isError": True}


def image_result(png_bytes, caption=None, mime="image/png"):
    content = [{"type": "image", "data": _b64(png_bytes), "mimeType": mime}]
    if caption:
        content.append({"type": "text", "text": caption})
    return {"content": content}


def _to_content(value):
    if value is None:
        return text_result("ok")
    if isinstance(value, dict) and "content" in value:
        return value
    if isinstance(value, str):
        return text_result(value)
    return text_result(json.dumps(value))


def _b64(data):
    return b64(data)


def b64(data):
    """Base64 als String -- auf dem Geraet ueber das eingebaute binascii."""
    try:
        import binascii
        return binascii.b2a_base64(bytes(data)).decode().strip()
    except ImportError:  # pragma: no cover
        import base64
        return base64.b64encode(bytes(data)).decode()


class McpServer:
    def __init__(self, tools, server_name="esp32-mcp", server_version="0.1.0",
                 instructions=None):
        self.tools = {t.name: t for t in tools}
        self.server_name = server_name
        self.server_version = server_version
        self.instructions = instructions
        self.initialized = False

    # -- JSON-RPC ---------------------------------------------------------
    def handle_message(self, msg):
        """Verarbeitet eine JSON-RPC-Nachricht. Rueckgabe: Antwort-dict oder None."""
        if not isinstance(msg, dict):
            return self._error(None, INVALID_REQUEST, "Nachricht ist kein Objekt")
        if isinstance(msg.get("method"), str) and "id" not in msg:
            return self._notification(msg)
        req_id = msg.get("id")
        method = msg.get("method")
        if not isinstance(method, str):
            return self._error(req_id, INVALID_REQUEST, "method fehlt")
        params = msg.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        try:
            result = self._dispatch(method, params)
        except MethodNotFound as exc:
            return self._error(req_id, METHOD_NOT_FOUND, str(exc))
        except InvalidParams as exc:
            return self._error(req_id, INVALID_PARAMS, str(exc))
        except Exception as exc:  # noqa: BLE001 - alles Unerwartete wird zur JSON-RPC-Fehlermeldung
            return self._error(req_id, INTERNAL_ERROR, "%s: %s" % (type(exc).__name__, exc))
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _notification(self, msg):
        if msg.get("method") == "notifications/initialized":
            self.initialized = True
        return None

    def _dispatch(self, method, params):
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [t.descriptor() for t in self.tools.values()]}
        if method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str):
                raise InvalidParams("name fehlt")
            tool = self.tools.get(name)
            if tool is None:
                raise InvalidParams("unbekanntes Tool: %s" % name)
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise InvalidParams("arguments muss ein Objekt sein")
            missing = [k for k in tool.schema.get("required", []) if k not in arguments]
            if missing:
                raise InvalidParams("fehlende Argumente: %s" % ", ".join(missing))
            return tool.call(arguments)
        if method in ("resources/list", "prompts/list"):
            key = "resources" if method.startswith("resources") else "prompts"
            return {key: []}
        raise MethodNotFound("nicht unterstuetzte Methode: %s" % method)

    def _initialize(self, params):
        wanted = params.get("protocolVersion")
        version = wanted if wanted in PROTOCOL_VERSIONS else DEFAULT_PROTOCOL
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": self.server_name, "version": self.server_version},
        }
        if self.instructions:
            result["instructions"] = self.instructions
        return result

    @staticmethod
    def _error(req_id, code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class MethodNotFound(Exception):
    pass


class InvalidParams(Exception):
    pass
