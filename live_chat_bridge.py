"""
live_chat_bridge.py
Real YouTube Live Chat integration for the Live Broadcast Studio:
  - Polls the live chat of your currently active YouTube broadcast
  - Auto-detects first-time commenters (tracked locally, per channel)
    and auto-posts a customizable welcome-template reply into the chat
  - Optionally translates incoming comments to Hindi for display

--------------------------------------------------------------------------
WHY A SEPARATE LOGIN FROM youtube_dashboard.py
--------------------------------------------------------------------------
Posting chat messages needs the broader `youtube.force-ssl` (read+write)
OAuth scope. youtube_dashboard.py only ever needs read-only analytics
scopes. Keeping them as separate logins follows least-privilege - you
don't have to grant write access to your channel just to view analytics,
and vice versa.

--------------------------------------------------------------------------
CLIENT ID/SECRET STORAGE - अब स्थायी (persistent) है
--------------------------------------------------------------------------
Streamlit Cloud पर filesystem "ephemeral" (अस्थायी) होता है - restart/
redeploy/sleep पर लिखी हुई local files मिट जाती हैं। इसलिए अब यह पहले
इस क्रम में देखता है, कहीं भी मिल जाए तो form दिखाना बंद हो जाता है:
    1) असली environment variables (YOUTUBE_CHAT_CLIENT_ID वगैरह)
    2) Streamlit Secrets [youtube_chat_oauth] section
    3) Streamlit Secrets [youtube_oauth] section (Dashboard वाला ही reuse)
    4) local file (सिर्फ़ testing के लिए, restart पर मिट जाएगी)

Streamlit Cloud पर स्थायी setup के लिए: Manage app → Settings → Secrets
में जोड़ें:
    [youtube_chat_oauth]
    client_id = "आपका Client ID"
    client_secret = "आपका Client Secret"
    redirect_uri = "https://your-app.streamlit.app/"

(अगर Dashboard वाला [youtube_oauth] पहले से Secrets में है, तो अलग से
कुछ जोड़ने की ज़रूरत नहीं - यह अपने आप उसी को reuse कर लेगा, क्योंकि
docstring में बताया गया है कि same Client ID/Secret दोनों जगह चल सकता
है, सिर्फ़ permission scope अलग होता है।)

--------------------------------------------------------------------------
LIMITATIONS - please read before relying on this
--------------------------------------------------------------------------
- YouTube has NO chat push/websocket API - this POLLS on the interval
  YouTube itself suggests (a few seconds), so there is always a small
  delay, never instant like a native chat client.
- "First-time commenter" is tracked ONLY within what THIS app has seen
  (stored in a local file) - it has no way to know someone's full
  YouTube-wide history, only whether they've commented in a chat this
  feature was monitoring since you turned it on.
- Hindi translation uses a free, UNOFFICIAL library (no Google Cloud
  Translation API key needed) - it's usually fine for casual text, but
  is not a paid/guaranteed service and can occasionally mistranslate
  slang or mixed Hindi-English (Hinglish) text.
- YouTube Data API has a daily quota. Heavy chat traffic + frequent
  polling can use it up faster than you'd expect - the polling interval
  below has a safety floor for this reason.

SETUP: same steps as youtube_dashboard.py's docstring (Google Cloud
project, enable "YouTube Data API v3"), but you can reuse the SAME
Client ID/Secret - the app will ask for the extra write scope on login.
"""

import os
import json
import time
import logging
import threading
from typing import Optional, List

# Google का OAuth कभी-कभी हमने जितना scope माँगा था उससे ज़्यादा दे देता
# है (जैसे Dashboard वाले readonly-scope login के साथ पहले से मिला हुआ
# broader youtube.force-ssl scope भी जुड़ जाना) - यह relax flag उस
# strict mismatch-check को हटाता है, ताकि यह गलती से error न बने।
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

logger = logging.getLogger("live_chat_bridge")

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    _GOOGLE_LIBS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _GOOGLE_LIBS_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    _TRANSLATOR_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TRANSLATOR_AVAILABLE = False
    logger.warning("deep-translator install nahi hai - Hindi translation unavailable. `pip install deep-translator` chalayein.")


SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".live_chat_data")
os.makedirs(CONFIG_DIR, exist_ok=True)
OAUTH_CONFIG_PATH = os.path.join(CONFIG_DIR, "oauth_config.json")
SEEN_COMMENTERS_PATH = os.path.join(CONFIG_DIR, "seen_commenters.json")
PENDING_OAUTH_PATH = os.path.join(CONFIG_DIR, "pending_oauth.json")

DEFAULT_WELCOME_TEMPLATE = (
    "🙏 Welcome to my channel! हमारे चैनल में जुड़ने व सपोर्ट के लिए आपको हृदय से धन्यवाद 🙏 "
    "चैनल को Like, Subscribe करें और कमेंट में हर हर महादेव 🔱 ज़रूर लिखें 🌺"
)


# ---------------------------------------------------------------------------
# Pending-OAuth (PKCE code_verifier) storage - keyed by the `state` value.
# See youtube_dashboard.py's identical helper for the full explanation:
# st.session_state does not reliably survive the real browser round-trip
# to Google's consent page and back, so this uses disk instead, keyed by
# the `state` param (which DOES survive, since it's just part of the URL).
# ---------------------------------------------------------------------------
def _save_pending_verifier(state: str, code_verifier: str):
    try:
        data = {}
        if os.path.exists(PENDING_OAUTH_PATH):
            with open(PENDING_OAUTH_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data[state] = code_verifier
        with open(PENDING_OAUTH_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def _pop_pending_verifier(state: str):
    try:
        if not os.path.exists(PENDING_OAUTH_PATH):
            return None
        with open(PENDING_OAUTH_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        verifier = data.pop(state, None)
        with open(PENDING_OAUTH_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return verifier
    except Exception:
        return None


MIN_POLL_INTERVAL_SEC = 5.0  # safety floor regardless of what YouTube suggests, to protect your API quota


# ---------------------------------------------------------------------------
# OAuth (separate credentials/session key from youtube_dashboard.py)
# ---------------------------------------------------------------------------
def _load_oauth_config():
    # 1) असली environment variables (सबसे सुरक्षित - self-hosted/local .env के लिए)
    env_client_id = os.environ.get("YOUTUBE_CHAT_CLIENT_ID")
    env_client_secret = os.environ.get("YOUTUBE_CHAT_CLIENT_SECRET")
    env_redirect_uri = os.environ.get("YOUTUBE_CHAT_REDIRECT_URI")
    if env_client_id and env_client_secret and env_redirect_uri:
        return {
            "client_id": env_client_id, "client_secret": env_client_secret,
            "redirect_uri": env_redirect_uri, "_source": "env",
        }

    # 2) Streamlit Secrets - पहले चैट-specific section देखें
    try:
        import streamlit as st
        if "youtube_chat_oauth" in st.secrets:
            s = st.secrets["youtube_chat_oauth"]
            return {
                "client_id": s.get("client_id", ""), "client_secret": s.get("client_secret", ""),
                "redirect_uri": s.get("redirect_uri", ""), "_source": "secrets",
            }
        # 3) न मिले तो Dashboard वाला [youtube_oauth] ही reuse कर लें
        # (docstring में बताया गया है कि same Client ID/Secret दोनों जगह
        # काम करता है, सिर्फ़ scope अलग माँगा जाता है)
        if "youtube_oauth" in st.secrets:
            s = st.secrets["youtube_oauth"]
            return {
                "client_id": s.get("client_id", ""), "client_secret": s.get("client_secret", ""),
                "redirect_uri": s.get("redirect_uri", ""), "_source": "secrets (dashboard से reuse)",
            }
    except Exception:
        pass

    # 4) आख़िर में local file (सिर्फ़ testing के लिए, restart पर मिट जाएगी)
    try:
        if os.path.exists(OAUTH_CONFIG_PATH):
            with open(OAUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_source"] = "file"
                return data
    except Exception:
        pass
    return {}


def _save_oauth_config(client_id, client_secret, redirect_uri):
    try:
        with open(OAUTH_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}, f)
    except Exception:
        pass


def _get_flow(client_id, client_secret, redirect_uri, code_verifier=None):
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    if code_verifier:
        # PKCE fix: reuse the SAME verifier the authorization_url() step
        # generated, instead of this fresh Flow generating (or lacking)
        # its own - Google rejects the token exchange otherwise with
        # "invalid_grant: Missing code verifier".
        flow.code_verifier = code_verifier
    return flow


def is_available() -> bool:
    return _GOOGLE_LIBS_AVAILABLE


def render_oauth_and_get_youtube_client(st):
    """
    Renders the (collapsed-by-default) setup expander + Login button, and
    returns a ready `youtube` API client once logged in, or None while
    still waiting on setup/login. `st` is passed in so this stays
    Streamlit-import-free at module load (mirrors youtube_dashboard.py).
    """
    if not _GOOGLE_LIBS_AVAILABLE:
        st.error("⚠️ ज़रूरी libraries install नहीं हैं। `pip install google-auth-oauthlib google-api-python-client`")
        return None

    saved = _load_oauth_config()

    if saved.get("_source") in ("env", "secrets", "secrets (dashboard से reuse)"):
        st.success(f"✅ Setup {saved['_source']} से load हुआ है — restart/redeploy/sleep के बाद भी सुरक्षित रहेगा।")
    else:
        with st.expander("⚙️ Live Chat के लिए Google Setup (लिखने की permission सहित)", expanded=not saved):
            st.warning(
                "⚠️ यह form-वाला तरीका सिर्फ़ local/testing के लिए है — Streamlit Cloud पर यहाँ भरी हुई "
                "value हर restart/redeploy/sleep पर मिट जाएगी। स्थायी setup के लिए **Streamlit Cloud → "
                "Manage app → Settings → Secrets** में `[youtube_chat_oauth]` के नीचे client_id, "
                "client_secret, redirect_uri डालें (या अगर Dashboard वाला `[youtube_oauth]` पहले से "
                "Secrets में है, तो कुछ जोड़ने की ज़रूरत ही नहीं, वही अपने आप reuse हो जाएगा) — फिर यह form "
                "अपने आप दिखना बंद हो जाएगा।"
            )
            st.caption(
                f"plain text में `{OAUTH_CONFIG_PATH}` में save होता है — `.gitignore` में ज़रूर जोड़ें। "
                "Dashboard वाला Client ID/Secret भी इस्तेमाल कर सकते हैं (बस login अलग से करना होगा, permission ज़्यादा चाहिए)।"
            )
            client_id = st.text_input("Client ID", value=saved.get("client_id", ""), key="chat_client_id")
            client_secret = st.text_input("Client Secret", value=saved.get("client_secret", ""), type="password", key="chat_client_secret")
            redirect_uri = st.text_input(
                "Redirect URI (Cloud Console में हूबहू यही)", value=saved.get("redirect_uri", ""),
                key="chat_redirect_uri", placeholder="https://your-app.streamlit.app/",
            )
            if st.button("💾 Save Setup", key="chat_oauth_save_btn"):
                _save_oauth_config(client_id, client_secret, redirect_uri)
                st.success("✅ Save हो गया (ध्यान दें: यह अगले restart तक ही रहेगा, ऊपर की चेतावनी देखें)।")
                st.rerun()

    if not (saved.get("client_id") and saved.get("client_secret") and saved.get("redirect_uri")):
        st.info("ℹ️ ऊपर Setup भरकर Save करें, फिर Login का बटन दिखेगा।")
        return None

    client_id, client_secret, redirect_uri = saved["client_id"], saved["client_secret"], saved["redirect_uri"]

    if "chat_credentials_json" in st.session_state:
        try:
            creds = Credentials.from_authorized_user_info(json.loads(st.session_state["chat_credentials_json"]), SCOPES)
            return build("youtube", "v3", credentials=creds)
        except Exception:
            del st.session_state["chat_credentials_json"]

    query_params = st.query_params
    if "code" in query_params:
        code = query_params["code"]
        state = query_params.get("state")
        already_processed = st.session_state.get("chat_oauth_processed_code")
        if code == already_processed:
            # Streamlit re-ran the script with the same ?code= still in the
            # URL - a Google auth code is single-use, re-submitting it
            # fails with "invalid_grant: Bad Request". Already handled it.
            st.query_params.clear()
            st.rerun()
        try:
            # Look the verifier up from disk by `state`, NOT session_state -
            # clicking the Login link is a real navigation to Google and
            # back, which can start a brand-new Streamlit session.
            code_verifier = _pop_pending_verifier(state) if state else None
            flow = _get_flow(client_id, client_secret, redirect_uri, code_verifier=code_verifier)
            flow.fetch_token(code=code)
            st.session_state["chat_credentials_json"] = flow.credentials.to_json()
            st.session_state["chat_oauth_processed_code"] = code
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.session_state["chat_oauth_processed_code"] = code  # don't retry this dead code in a loop
            st.error(
                f"❌ Login fail हुआ: {e}\n\n"
                "अगर यह दोबारा हो, तो नीचे दोबारा Login बटन दबाकर एक बिल्कुल नई कोशिश करें "
                "(पुराना redirect link दोबारा खोलने या बैक-बटन इस्तेमाल करने से बचें)।"
            )
            return None

    flow = _get_flow(client_id, client_secret, redirect_uri)
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline", include_granted_scopes="true")
    # Save this exact Flow's code_verifier to disk, keyed by `state` - this
    # is the PKCE fix, done in a way that survives the real redirect to
    # Google and back.
    _save_pending_verifier(state, flow.code_verifier)
    st.link_button("🔓 Live Chat के लिए Login करें (लिखने की permission सहित)", auth_url)
    return None


# ---------------------------------------------------------------------------
# Seen-commenters persistence (for "first-time" detection)
# ---------------------------------------------------------------------------
def _load_seen_commenters() -> set:
    try:
        if os.path.exists(SEEN_COMMENTERS_PATH):
            with open(SEEN_COMMENTERS_PATH, "r", encoding="utf-8") as f:
                return set(json.load(f))
    except Exception:
        pass
    return set()


def _save_seen_commenters(seen: set):
    try:
        with open(SEEN_COMMENTERS_PATH, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False)
    except Exception:
        pass


def reset_seen_commenters():
    """Wipes the 'first-time commenter' memory - useful for testing, or
    if you want everyone treated as new again for a fresh event."""
    _save_seen_commenters(set())


# ---------------------------------------------------------------------------
# Translation (free, unofficial - see limitations in module docstring)
# ---------------------------------------------------------------------------
def translate_to_hindi(text: str) -> str:
    if not text or not text.strip():
        return text
    if not _TRANSLATOR_AVAILABLE:
        return text
    try:
        return GoogleTranslator(source="auto", target="hi").translate(text)
    except Exception:
        return text  # translation failed - show the original rather than lose the message


# ---------------------------------------------------------------------------
# Live chat monitor - background thread, independent of Streamlit reruns
# ---------------------------------------------------------------------------
class LiveChatMonitor:
    def __init__(self, youtube, welcome_template: str, auto_welcome_enabled: bool, translate_enabled: bool):
        self.youtube = youtube
        self.welcome_template = welcome_template
        self.auto_welcome_enabled = auto_welcome_enabled
        self.translate_enabled = translate_enabled
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._live_chat_id: Optional[str] = None
        self._page_token: Optional[str] = None
        self._seen_commenters = _load_seen_commenters()
        self._messages: List[dict] = []
        self._lock = threading.Lock()
        self._last_error: Optional[str] = None
        self.welcomed_count = 0

    def _resolve_live_chat_id(self) -> Optional[str]:
        resp = self.youtube.liveBroadcasts().list(part="snippet", broadcastStatus="active", broadcastType="all").execute()
        items = resp.get("items", [])
        if not items:
            return None
        return items[0]["snippet"].get("liveChatId")

    def start(self) -> bool:
        if self._running:
            return True
        try:
            self._live_chat_id = self._resolve_live_chat_id()
        except Exception as e:
            self._last_error = f"Active live broadcast nahi mila: {e}"
            return False
        if not self._live_chat_id:
            self._last_error = "Koi active live broadcast nahi mila is channel par. Pehle YouTube par live shuru karein, phir yahan connect karein."
            return False
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="LiveChatMonitor", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False

    def _post_message(self, text: str) -> bool:
        try:
            self.youtube.liveChatMessages().insert(
                part="snippet",
                body={
                    "snippet": {
                        "liveChatId": self._live_chat_id,
                        "type": "textMessageEvent",
                        "textMessageDetails": {"messageText": text},
                    }
                },
            ).execute()
            return True
        except Exception as e:
            logger.exception("Chat message post karne mein fail hui.")
            self._last_error = str(e)
            return False

    def post_message(self, text: str) -> bool:
        """Public: send any message into the live chat (not just the
        auto-welcome) - e.g. a manual reply typed by you in the UI."""
        return self._post_message(text)

    def _run_loop(self):
        interval = MIN_POLL_INTERVAL_SEC
        while self._running:
            try:
                resp = self.youtube.liveChatMessages().list(
                    liveChatId=self._live_chat_id, part="snippet,authorDetails",
                    pageToken=self._page_token,
                ).execute()
                suggested = resp.get("pollingIntervalMillis", 5000) / 1000.0
                interval = max(MIN_POLL_INTERVAL_SEC, suggested)
                self._page_token = resp.get("nextPageToken")

                for item in resp.get("items", []):
                    author = item.get("authorDetails", {})
                    snippet = item.get("snippet", {})
                    display_name = author.get("displayName", "Viewer")
                    channel_id = author.get("channelId", "")
                    original_text = snippet.get("displayMessage", "")
                    shown_text = translate_to_hindi(original_text) if self.translate_enabled else original_text

                    with self._lock:
                        self._messages.append({
                            "author": display_name,
                            "text": shown_text,
                            "original_text": original_text,
                            "translated": self.translate_enabled and shown_text != original_text,
                        })
                        if len(self._messages) > 200:
                            self._messages = self._messages[-200:]

                    if self.auto_welcome_enabled and channel_id and channel_id not in self._seen_commenters:
                        self._seen_commenters.add(channel_id)
                        _save_seen_commenters(self._seen_commenters)
                        if self._post_message(self.welcome_template):
                            self.welcomed_count += 1

            except Exception as e:
                logger.exception("Chat poll mein error.")
                self._last_error = str(e)
                time.sleep(MIN_POLL_INTERVAL_SEC)
                continue

            time.sleep(interval)

    def get_messages(self) -> List[dict]:
        with self._lock:
            return list(self._messages)

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def is_running(self) -> bool:
        return self._running


_monitor: Optional[LiveChatMonitor] = None
_monitor_lock = threading.Lock()


def start_chat_monitor(youtube, welcome_template: str, auto_welcome_enabled: bool, translate_enabled: bool) -> bool:
    global _monitor
    with _monitor_lock:
        if _monitor is not None and _monitor.is_running:
            return False
        m = LiveChatMonitor(youtube, welcome_template, auto_welcome_enabled, translate_enabled)
        if not m.start():
            _last = m.get_last_error()
            logger.error(_last)
            return False
        _monitor = m
        return True


def stop_chat_monitor():
    global _monitor
    with _monitor_lock:
        if _monitor is not None:
            _monitor.stop()
            _monitor = None


def get_chat_messages() -> List[dict]:
    if _monitor is not None:
        return _monitor.get_messages()
    return []


def send_chat_message(text: str) -> bool:
    if _monitor is not None:
        return _monitor.post_message(text)
    return False


def is_monitoring() -> bool:
    return _monitor is not None and _monitor.is_running


def get_monitor_error() -> Optional[str]:
    if _monitor is not None:
        return _monitor.get_last_error()
    return None


def get_welcomed_count() -> int:
    if _monitor is not None:
        return _monitor.welcomed_count
    return 0
