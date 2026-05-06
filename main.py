from flask import Flask, request, jsonify
import json
import uuid
import requests
import websocket
import threading
import os

app = Flask(__name__)

class CopilotClient:
    def __init__(self):
        self.session = requests.Session()
        self.client_id = str(uuid.uuid4())
        self.conversation_id = None
        self._start_conversation()

    def _start_conversation(self):
        url = "https://copilot.microsoft.com/c/api/start"

        payload = {
            "timeZone": "Asia/Dhaka",
            "startNewConversation": True,
            "teenSupportEnabled": True,
            "correctPersonalizationSetting": True,
            "deferredDataUseCapable": True
        }

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "X-Search-UILang": "en-US"
        }

        r = self.session.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()

        self.conversation_id = r.json()["currentConversationId"]

    def ask(self, message: str):
        ws_url = f"wss://copilot.microsoft.com/c/api/chat?api-version=2&clientSessionId={self.client_id}"

        cookies = "; ".join(
            [f"{k}={v}" for k, v in self.session.cookies.get_dict().items()]
        )

        result = {
            "text": "",
            "message_id": None
        }

        done_event = threading.Event()

        def send_message(ws):
            ws.send(json.dumps({
                "event": "send",
                "content": [{"type": "text", "text": message}],
                "conversationId": self.conversation_id
            }))

        def on_open(ws):
            send_message(ws)

        def on_message(ws, msg):
            try:
                data = json.loads(msg)

                if data.get("event") == "startMessage":
                    result["message_id"] = data["messageId"]

                elif data.get("event") == "appendText":
                    if data.get("messageId") == result["message_id"]:
                        text = data.get("text", "")
                        result["text"] += text

                elif data.get("event") == "done":
                    ws.close()
                    done_event.set()

            except Exception:
                pass

        def on_error(ws, err):
            result["text"] = f"ERROR: {err}"
            done_event.set()

        ws = websocket.WebSocketApp(
            ws_url,
            header=[
                f"Cookie: {cookies}",
                "User-Agent: Mozilla/5.0",
                "X-Search-UILang: en-US"
            ],
            on_open=on_open,
            on_message=on_message,
            on_error=on_error
        )

        thread = threading.Thread(target=ws.run_forever)
        thread.daemon = True
        thread.start()

        done_event.wait(timeout=60)

        text = result["text"].strip()

        if not text:
            raise Exception("Empty response")

        return text


bot = CopilotClient()


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "location": "Bangladesh"
    })


@app.route("/api/ask")
def ask():
    prompt = request.args.get("prompt", "").strip()

    if not prompt:
        return jsonify({
            "error": "No prompt provided"
        }), 400

    try:
        answer = bot.ask(prompt)

        return jsonify({
            "response": answer
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
