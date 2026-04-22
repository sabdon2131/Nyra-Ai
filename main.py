from flask import Flask, request, jsonify
import requests
import json
import os

app = Flask(__name__)

# ----------------------------
# MEMORY FILES
# ----------------------------
def ensure_file(file_name, default='{}'):
    if not os.path.exists(file_name):
        with open(file_name,'w') as f:
            f.write(default)

ensure_file('commands.json')
ensure_file('preferences.json')
ensure_file('rules.json')

def load_json(file_name, default):
    try:
        with open(file_name,"r") as f:
            return json.load(f)
    except:
        return default

def save_json(file_name,data):
    with open(file_name,"w") as f:
        json.dump(data,f,indent=2)

COMMANDS = load_json("commands.json", {})

# ----------------------------
# GLOBAL MEMORY
# ----------------------------
conversation_history = []

# ----------------------------
# OPENROUTER KEY
# ----------------------------
OPENROUTER_API_KEY = "your api key"

# ----------------------------
# SYSTEM PROMPT
# ----------------------------
SYSTEM_PROMPT = """
You are an AI assistant.
If user requests an action, respond ONLY in JSON:
{
  "type": "command",
  "action": "open_app",
  "value": "appname"
}
Otherwise respond normally.
"""

# ----------------------------
# HOME
# ----------------------------
@app.route("/")
def home():
    return "NYRA AI Running"

# ----------------------------
# ASK ROUTE (MAIN BRAIN)
# ----------------------------
@app.route("/ask", methods=["POST"])
def ask():
    data = request.json or {}

    user_text = data.get("text", "")

    if not user_text:
        return jsonify({"response": "No input provided"})

    user_lower = user_text.lower().strip()

    # learned commands
    if user_lower in COMMANDS:
        package = COMMANDS[user_lower]
        os.system(f"am start -n {package}")
        return jsonify({"response": f"Opening {user_text}"})

    # build detection
    is_build_request = any(
        word in user_lower
        for word in ["build", "create", "app", "website", "bot", "system", "project"]
    )

    system_content = SYSTEM_PROMPT

    if is_build_request:
        system_content += "\nReturn ONLY JSON with project structure."

    conversation_history.append({
        "role": "user",
        "content": user_text
    })

    messages = [
        {"role": "system", "content": system_content}
    ] + conversation_history[-10:]

    url = "https://openrouter.ai/api/v1/chat/completions"

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": "AI Assistant"
            },
            json={
                "model": "meta-llama/llama-3-8b-instruct",
                "messages": messages
            },
            timeout=20
        )

        data = response.json()

        if "choices" in data:
            ai_text = data["choices"][0]["message"]["content"]
        elif "error" in data:
            ai_text = "API Error: " + str(data["error"])
        else:
            ai_text = "Unknown API response"

    except Exception as e:
        ai_text = "Request failed: " + str(e)

    conversation_history.append({
        "role": "assistant",
        "content": ai_text
    })

    # command execution
    try:
        cmd = json.loads(ai_text)

        if cmd.get("type") == "command":
            action = cmd.get("action")
            value = cmd.get("value")

            APP_MAP = {
                "youtube": "com.google.android.youtube/.HomeActivity",
                "whatsapp": "com.whatsapp/.HomeActivity",
                "chrome": "com.android.chrome/com.google.android.apps.chrome.Main",
                "instagram": "com.instagram.android/.activity.MainTabActivity"
            }

            if action == "open_app":
                package = APP_MAP.get(value.lower())

                if package:
                    os.system(f"am start -n {package}")
                    return jsonify({"response": f"Opening {value}"})

                return jsonify({"response": "App not found"})

    except:
        pass

    return jsonify({"response": ai_text})

# ----------------------------
# UI
# ----------------------------
@app.route('/ui')
def ui():
    return """
<html>
<head>
<title>NYRA</title>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>

<style>
body{
background:#111;
color:white;
font-family:Arial;
text-align:center;
padding:20px;
}

input{
width:80%;
padding:10px;
margin:10px;
border-radius:8px;
border:none;
}

button{
padding:10px 15px;
margin:5px;
background:#00ffcc;
border:none;
border-radius:8px;
cursor:pointer;
}

#response{
margin-top:20px;
white-space:pre-wrap;
}
</style>
</head>

<body>

<h2>NYRA AI</h2>

<input id='input' type='text' placeholder='Speak or type...'>
<br>

<button onclick='startVoice()'>🎤 Speak</button>
<button onclick='send()'>Send</button>
<button onclick='toggleAssistant()'>🔁 Assistant Mode</button>

<p id='response'></p>

<script>

let assistantActive = false;
let isSpeaking = false;
let recognition = null;

// ----------------------
// SPEECH RECOGNITION
// ----------------------
function getRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let rec = new SpeechRecognition();

    rec.lang = "en-US";
    rec.continuous = false;
    rec.interimResults = false;

    rec.onstart = function () {
        document.getElementById("response").innerText = "Listening...";
    };

    rec.onresult = function (event) {
        let text = event.results[0][0].transcript;
        document.getElementById("input").value = text;
        send();
    };

    rec.onerror = function (e) {
        document.getElementById("response").innerText = "Voice error: " + e.error;
    };

    rec.onend = function () {
        if (assistantActive && !isSpeaking) {
            setTimeout(() => {
                if (!window.speechSynthesis.speaking) {
                    startVoice();
                }
            }, 1200);
        }
    };

    return rec;
}

// ----------------------
// START VOICE
// ----------------------
function startVoice() {
    if (isSpeaking) return;
    if (window.speechSynthesis.speaking) return;

    if (!recognition) {
        recognition = getRecognition();
    }

    try {
        recognition.start();
    } catch (e) {
        recognition = getRecognition();
        recognition.start();
    }
}

// ----------------------
// TOGGLE ASSISTANT
// ----------------------
function toggleAssistant() {
    assistantActive = !assistantActive;

    document.getElementById("response").innerText =
        assistantActive ? "Assistant ON" : "Assistant OFF";

    if (assistantActive) {
        startVoice();
    } else {
        window.speechSynthesis.cancel();
        if (recognition) recognition.stop();
    }
}

// ----------------------
// SEND FUNCTION
// ----------------------
function send() {
    let text = document.getElementById("input").value;
    if (!text.trim()) return;

    document.getElementById("response").innerText = "Thinking...";

    fetch(window.location.origin + "/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text })
    })
    .then(res => res.json())
    .then(data => {

        let reply = data.response;

        document.getElementById("response").innerText = reply;

        if (recognition) {
            recognition.stop();
        }

        isSpeaking = true;
        window.speechSynthesis.cancel();

        let speech = new SpeechSynthesisUtterance(reply);
        speech.lang = "en-US";

        speech.onend = function () {
            isSpeaking = false;

            if (assistantActive) {
                setTimeout(() => {
                    if (!window.speechSynthesis.speaking) {
                        startVoice();
                    }
                }, 1200);
            }
        };

        window.speechSynthesis.speak(speech);
    })
    .catch(err => {
        document.getElementById("response").innerText = "Error: " + err;
    });
}

</script>

</body>
</html>
"""

# ----------------------------
# RUN SERVER
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)