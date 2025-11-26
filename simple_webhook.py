#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template_string, Response, redirect, url_for
import datetime
import json
import queue
import uuid
import time

app = Flask(__name__)

# Struktur session untuk multi-user support
SESSIONS = {}
SESSION_TIMEOUT = 3600  # 1 jam
MAX_LOGS_PER_SESSION = 100

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simple Webhook</title>
    <link rel="shortcut icon" href="{{ url_for('static', filename='favicon.ico') }}">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f9f9f9;
        }
        h2 {
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }
        pre {
            background: #f5f5f5;
            padding: 10px;
            border-radius: 5px;
            overflow-x: auto;
            font-size: 12px;
        }
        .card {
            border: 1px solid #ddd;
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 8px;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            font-family: monospace;
            font-size: 13px;
        }
        .card strong {
            color: #555;
        }
        .method {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
        }
        .method-GET { background: #28a745; color: white; }
        .method-POST { background: #007bff; color: white; }
        .method-PUT { background: #ffc107; color: black; }
        .method-PATCH { background: #17a2b8; color: white; }
        .method-DELETE { background: #dc3545; color: white; }
        .method-OPTIONS { background: #6c757d; color: white; }
        .method-HEAD { background: #e0e2e6; color: black; }
        .connection-status {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        .connected { background: #28a745; color: white; }
        .disconnected { background: #dc3545; color: white; }
        .clear-btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 4px;
            cursor: pointer;
        }
        .clear-btn:hover {
            background: #c82333;
        }
        .new-session-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 4px;
            cursor: pointer;
        }
        .new-session-btn:hover {
            background: #218838;
        }
        .url-box {
            background: #fff;
            border: 2px solid #007bff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }
        .url-box h3 {
            margin-top: 0;
            color: #007bff;
            font-size: 16px;
        }
        .url-input {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-family: monospace;
            font-size: 13px;
            margin-bottom: 10px;
            box-sizing: border-box;
        }
        .copy-btn {
            background: #007bff;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 4px;
            cursor: pointer;
        }
        .copy-btn:hover {
            background: #0056b3;
        }
        .copy-btn.copied {
            background: #28a745;
        }
        .info {
            font-family: monospace;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div id="connection-status" class="connection-status disconnected">● Connecting...</div>

    <h2>Simple Webhook</h2>

    <div class="url-box">
        <h3>📨 Send requests to this address:</h3>
        <input type="text" id="webhook-url" class="url-input" readonly value="{{ webhook_url }}">
        <button class="copy-btn" onclick="copyWebhookUrl()">Copy URL</button>
        <button class="new-session-btn" onclick="createNewSession()">New Session</button>
        <button class="clear-btn" onclick="clearLogs()">Clear Logs</button>
    </div>

    <div id="log-container">
        {% for log in logs %}
            <div class="card">
                <strong>Datetime__:</strong> {{ log.time }}<br>
                <strong>Client_IP_:</strong> {{ log.client_ip }}<br>
                <strong>Path______:</strong> {{ log.path }}<br>
                <strong>Method____:</strong> <span class="method method-{{ log.method }}">{{ log.method }}</span><br>
                <br>
                <strong>Headers:</strong>
                <pre>{{ log.headers }}</pre>
                <strong>Query Params:</strong>
                <pre>{{ log.query }}</pre>
                <strong>Body:</strong>
                <pre>{{ log.body }}</pre>
            </div>
        {% endfor %}
    </div>

<script>
const SESSION_ID = "{{ session_id }}";
localStorage.setItem("webhook_session_id", SESSION_ID);

const statusEl = document.getElementById("connection-status");

let evtSource;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

try {
    evtSource = new EventSource("/stream/" + SESSION_ID);
    console.log("Creating SSE connection for session:", SESSION_ID);
} catch (e) {
    console.error("Failed to create SSE connection:", e);
    statusEl.textContent = "● Error";
    statusEl.className = "connection-status disconnected";
}

if (evtSource) {
    evtSource.onopen = function() {
        statusEl.textContent = "● Connected";
        statusEl.className = "connection-status connected";
        reconnectAttempts = 0;
        console.log("SSE Connected to session:", SESSION_ID);
    };

    evtSource.onerror = function(e) {
        console.error("SSE error - readyState:", evtSource.readyState, "event:", e);

        if (evtSource.readyState === EventSource.CONNECTING) {
            statusEl.textContent = "● Reconnecting...";
            statusEl.className = "connection-status disconnected";
            reconnectAttempts++;

            if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
                statusEl.textContent = "● Connection Failed";
                evtSource.close();
            }
        } else if (evtSource.readyState === EventSource.CLOSED) {
            statusEl.textContent = "● Connection Lost";
            statusEl.className = "connection-status disconnected";

            setTimeout(async () => {
                try {
                    const response = await fetch("/health");
                    if (response.ok) {
                        statusEl.textContent = "● Session Expired - Refresh page";
                    } else {
                        statusEl.textContent = "● Server Error";
                    }
                } catch (err) {
                    console.error("Health check failed:", err);
                    statusEl.textContent = "● Server Offline";
                }
            }, 1000);
        }
    };

    evtSource.onmessage = function(event) {
        const data = JSON.parse(event.data);

        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
            <strong>Datetime__:</strong> ${data.time}<br>
            <strong>Client_IP_:</strong> <span class="Client_IP">${escapeHtml(data.client_ip)}</span><br>
            <strong>Path______:</strong> ${data.path}<br>
            <strong>Method____:</strong> <span class="method method-${data.method}">${data.method}</span><br>
            <br>
            <strong>Headers:</strong>
            <pre>${escapeHtml(data.headers)}</pre>
            <strong>Query Params:</strong>
            <pre>${escapeHtml(data.query)}</pre>
            <strong>Body:</strong>
            <pre>${escapeHtml(data.body)}</pre>
        `;

        const cont = document.getElementById("log-container");
        cont.prepend(card);

        while (cont.children.length > 100) {
            cont.removeChild(cont.lastChild);
        }
    };

    evtSource.addEventListener('error', function(event) {
        if (event.data) {
            const errorData = JSON.parse(event.data);
            console.error("Server error:", errorData);
            alert("Session error: " + errorData.error + ". Refresh the page, please.");
        }
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function clearLogs() {
    if (confirm('Clear logs?')) {
        document.getElementById("log-container").innerHTML = '';
    }
}

function copyWebhookUrl() {
    const input = document.getElementById("webhook-url");
    input.select();
    document.execCommand("copy");
}

function createNewSession() {
    if (confirm('Create a new session? The old session will remain active.')) {
        localStorage.removeItem("webhook_session_id");
        window.location.href = "/";
    }
}
</script>
</body>
</html>
"""


def get_or_create_session(session_id=None):
    """Mendapatkan atau membuat session baru"""
    if session_id and session_id in SESSIONS:
        SESSIONS[session_id]["last_access"] = time.time()
        return session_id

    if session_id:
        SESSIONS[session_id] = {
            "queue": queue.Queue(),
            "logs": [],
            "created": time.time(),
            "last_access": time.time()
        }
        print(f"✨ Session recreated: {session_id}")
        return session_id

    new_session_id = str(uuid.uuid4())
    SESSIONS[new_session_id] = {
        "queue": queue.Queue(),
        "logs": [],
        "created": time.time(),
        "last_access": time.time()
    }
    print(f"✨ New session created: {new_session_id}")
    return new_session_id


def cleanup_old_sessions():
    """Hapus session yang sudah tidak aktif"""
    current_time = time.time()
    expired_sessions = [
        sid for sid, data in SESSIONS.items()
        if current_time - data["last_access"] > SESSION_TIMEOUT
    ]
    for sid in expired_sessions:
        del SESSIONS[sid]


def get_client_ip():
    """Mendapatkan IP address client dengan mempertimbangkan proxy"""
    # Cek X-Forwarded-For header (untuk proxy/load balancer)
    if request.headers.get('X-Forwarded-For'):
        # X-Forwarded-For bisa berisi multiple IP, ambil yang pertama
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    # Cek X-Real-IP header (nginx)
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
    # Cek CF-Connecting-IP (Cloudflare)
    elif request.headers.get('CF-Connecting-IP'):
        ip = request.headers.get('CF-Connecting-IP')
    # Fallback ke remote_addr
    else:
        ip = request.remote_addr
    return ip


def get_base_url():
    """Return correct base URL (supports reverse proxy HTTPS)"""
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    return f"{proto}://{host}"


@app.route("/")
def viewer_root():
    """Root endpoint - redirect ke session baru"""
    session_id = get_or_create_session()
    cleanup_old_sessions()
    return redirect(f"/{session_id}", code=302)


@app.route("/<session_id>")
def viewer_session(session_id):
    """Viewer untuk session tertentu"""
    if session_id not in SESSIONS:
        get_or_create_session(session_id)

    cleanup_old_sessions()
    logs = SESSIONS[session_id]["logs"]

    base_url = get_base_url()
    webhook_url = f"{base_url}/webhook/{session_id}"
    viewer_url = f"{base_url}/{session_id}"

    return render_template_string(
        HTML_TEMPLATE,
        logs=logs,
        session_id=session_id,
        webhook_url=webhook_url,
        viewer_url=viewer_url
    )


@app.route("/stream/<session_id>")
def stream(session_id):
    """SSE stream untuk session tertentu"""
    if session_id not in SESSIONS:
        get_or_create_session(session_id)

        if session_id not in SESSIONS:
            def error_stream():
                yield f"event: error\ndata: {json.dumps({'error': 'Session expired or invalid'})}\n\n"
            return Response(
                error_stream(),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive"
                }
            )

    def event_stream():
        q = SESSIONS[session_id]["queue"]
        last_heartbeat = time.time()

        while True:
            try:
                data = q.get(timeout=10)
                yield f"data: {json.dumps(data)}\n\n"
                last_heartbeat = time.time()
            except queue.Empty:
                current_time = time.time()
                if current_time - last_heartbeat >= 10:
                    yield ": heartbeat\n\n"
                    last_heartbeat = current_time

                if session_id not in SESSIONS:
                    yield f"event: error\ndata: {json.dumps({'error': 'Session expired'})}\n\n"
                    break
            except Exception as e:
                print(f"Stream error for session {session_id}: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                break

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


@app.route('/favicon.ico')
def favicon():
    return url_for('static', filename='favicon.ico')


@app.after_request
def add_headers(response):
    """Tambahkan header no-cache"""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def extract_query(req):
    """Ekstrak query parameters"""
    if not req.args:
        return "(none)"
    return "\n".join([f"{k}={v}" for k, v in req.args.items()])


def extract_body(req):
    """Ekstrak body request dengan berbagai format"""
    if req.form:
        return "\n".join([f"{k}={v}" for k, v in req.form.items()])

    if req.files:
        info = []
        for name, file in req.files.items():
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)
            info.append(
                f"{name}: filename={file.filename}, "
                f"size={size} bytes, content_type={file.content_type}"
            )
        return "\n".join(info)

    json_body = req.get_json(silent=True)
    if json_body is not None:
        return json.dumps(json_body, indent=2, ensure_ascii=False)

    raw = req.data.decode("utf-8", errors="ignore")
    return raw if raw else "(empty)"


@app.route("/webhook/<session_id>", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.route("/webhook/<session_id>/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def receiver(session_id, path):
    """Endpoint webhook receiver"""
    if not session_id or session_id not in SESSIONS:
        return jsonify({
            "error": "Invalid or missing session_id",
            "hint": "Use /webhook/YOUR_SESSION_ID"
        }), 400

    body = extract_body(request)
    query = extract_query(request)
    client_ip = get_client_ip()

    log_entry = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "client_ip": client_ip,
        "method": request.method,
        "path": f"/webhook/{session_id}/{path}" if path else f"/webhook/{session_id}",
        "headers": "\n".join([f"{k}: {v}" for k, v in request.headers.items()]),
        "body": body,
        "query": query,
    }

    session = SESSIONS[session_id]
    session["logs"].insert(0, log_entry)
    session["last_access"] = time.time()

    if len(session["logs"]) > MAX_LOGS_PER_SESSION:
        session["logs"] = session["logs"][:MAX_LOGS_PER_SESSION]

    try:
        session["queue"].put_nowait(log_entry)
    except queue.Full:
        pass

    return jsonify({
        "status": "ok",
        "realtime": True,
        "session_id": session_id,
        "client_ip": client_ip
    })


@app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "active_sessions": len(SESSIONS),
        "timestamp": datetime.datetime.now().isoformat()
    })


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Simple Webhook")
    print("=" * 60)
    print("\n📍 Viewer : http://0.0.0.0:8080")
    print("📨 Webhook: http://0.0.0.0:8080/webhook/YOUR_SESSION_ID")
    print("💚 Health check: http://0.0.0.0:8080/health")
    print("\n" + "=" * 60 + "\n")

    app.run(host="0.0.0.0", port=8080, threaded=True, debug=False)
