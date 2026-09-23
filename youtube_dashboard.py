"""
youtube_dashboard.py
"📊 Business Dashboard" mode - a YouTube channel growth/monetization
dashboard, using YouTube's OWN official APIs (Data API v3 + Analytics
API v2) via OAuth2. Call render_dashboard_ui() from app.py.

--------------------------------------------------------------------------
यह वर्ज़न business_report.py और topic_trend_analysis.py के साथ पहले से
जुड़ा (integrated) है — बस इन दोनों फ़ाइलों को इसी फ़ोल्डर में रखें,
कुछ और नहीं करना है।
--------------------------------------------------------------------------

WHAT THIS CAN AND CANNOT DO - PLEASE READ
--------------------------------------------------------------------------
CAN (real, verified data straight from YouTube's own APIs):
    - Your channel's real subscriber count, total views, video count
    - Real daily views / watch-time / likes / subscriber-gain charts
      for any date range, pulled from YouTube Analytics
    - Your top-performing videos/Shorts in a period, by views or watch time
    - A monetization-progress tracker comparing your real numbers
      against YouTube Partner Program thresholds (verified Jan 2026):
        Early Access: 500 subs + 3 public uploads + (3,000 watch hours/
                      12mo OR 3M Shorts views/90 days)
        Full Monetization: 1,000 subs + (4,000 watch hours/12mo OR
                      10M Shorts views/90 days) - rising to 8,000/20M
                      on 1 Feb 2027
    - What's currently getting high views in a niche/keyword you choose
      (via public YouTube search) - as INSPIRATION, not a guarantee
    - एक हिंदी "व्यापार रिपोर्ट" जो बताए क्या सही हुआ, क्या सुधार चाहिए,
      निष्कर्ष और आगे की रणनीति (business_report.py)
    - टॉपिक/फॉर्मेट (Shorts बनाम Long-form) के हिसाब से आपके वीडियो का
      परफॉर्मेंस, और पूरे niche में क्या ज़्यादा चल रहा है
      (topic_trend_analysis.py)

CANNOT (no tool, including this one, can honestly offer these):
    - "Secret" growth hacks or guaranteed-viral hashtags/titles -
      YouTube's ranking algorithm is private; nobody outside YouTube
      knows it, and any claim otherwise is not credible
    - A live "trending hashtags" feed - YouTube has no public API for
      this; the "Niche Trend Explorer" below is a best-effort proxy
      (recent high-view videos matching your keywords), not real trends
    - Automatic content posting/scheduling based on "trends" - this
      module is read-only (analytics + research), it does not upload,
      edit, or auto-publish anything to your channel

SETUP REQUIRED (one-time, you do this yourself in Google Cloud Console -
Claude cannot do this on your behalf, it requires your Google login):
    1. console.cloud.google.com -> create/select a project
    2. APIs & Services -> Library -> enable "YouTube Data API v3" AND
       "YouTube Analytics API"
    3. APIs & Services -> Credentials -> Create Credentials -> OAuth
       client ID -> Application type: "Web application"
    4. Under "Authorized redirect URIs", add the exact URL this app is
       served at (e.g. https://your-app.streamlit.app/) - it must match
       EXACTLY what you enter as Redirect URI below, trailing slash and
       all
    5. Copy the Client ID and Client Secret into the boxes below
--------------------------------------------------------------------------
"""

import os
import json
import logging
from datetime import datetime, timedelta

import streamlit as st

from business_report import render_business_report
from topic_trend_analysis import render_own_topic_performance, render_niche_intelligence

# Google का OAuth कभी-कभी हमने जितना scope माँगा था उससे ज़्यादा दे देता
# है - जैसे अगर उसी Client ID/Google account से पहले से Live Chat
# (youtube.force-ssl) login किया गया है, तो include_granted_scopes=true
# की वजह से वह पहले वाला broader scope भी दोबारा जोड़कर लौटा देता है।
# डिफ़ॉल्ट रूप से यह library इसे error मान लेती है, भले ही extra
# permission नुकसानदायक न हो। यह relax flag उस strict check को हटाता है।
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

logger = logging.getLogger("youtube_dashboard")

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    _GOOGLE_LIBS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _GOOGLE_LIBS_AVAILABLE = False


SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# Verified against YouTube's own eligibility pages, January 2026.
YPP_THRESHOLDS = {
    "early_access": {"subs": 500, "watch_hours_365d": 3000, "shorts_views_90d": 3_000_000, "min_uploads": 3},
    "full_monetization": {"subs": 1000, "watch_hours_365d": 4000, "shorts_views_90d": 10_000_000},
    "full_monetization_from_2027_02_01": {"subs": 1000, "watch_hours_365d": 8000, "shorts_views_90d": 20_000_000},
}

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".dashboard_data")
os.makedirs(CONFIG_DIR, exist_ok=True)
OAUTH_CONFIG_PATH = os.path.join(CONFIG_DIR, "oauth_config.json")
PENDING_OAUTH_PATH = os.path.join(CONFIG_DIR, "pending_oauth.json")


# ---------------------------------------------------------------------------
# OAuth config persistence (Client ID/Secret only - NEVER the token itself)
# ---------------------------------------------------------------------------
def _load_oauth_config():
    # 1) सबसे पहले असली environment variables देखें - self-hosted या local
    #    .env (python-dotenv से load किया हुआ) के लिए यह सबसे सुरक्षित है,
    #    क्योंकि यह कभी GitHub repo में नहीं जाता।
    env_client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    env_client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    env_redirect_uri = os.environ.get("YOUTUBE_REDIRECT_URI")
    if env_client_id and env_client_secret and env_redirect_uri:
        return {
            "client_id": env_client_id, "client_secret": env_client_secret,
            "redirect_uri": env_redirect_uri, "_source": "env",
        }

    # 2) फिर Streamlit Cloud के Secrets में देखें - यह ephemeral filesystem
    #    पर save नहीं होता (restart/redeploy/sleep पर भी सुरक्षित रहता है)।
    try:
        if "youtube_oauth" in st.secrets:
            s = st.secrets["youtube_oauth"]
            return {
                "client_id": s.get("client_id", ""),
                "client_secret": s.get("client_secret", ""),
                "redirect_uri": s.get("redirect_uri", ""),
                "_source": "secrets",
            }
    except Exception:
        pass

    # 3) आख़िर में local file (सिर्फ़ testing के लिए, restart पर मिट जाएगी)
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


# ---------------------------------------------------------------------------
# Pending-OAuth (PKCE code_verifier) storage - keyed by the `state` value.
#
# WHY THIS EXISTS: st.session_state does NOT reliably survive the trip to
# Google's consent page and back - clicking a link_button is a real
# browser navigation to a different domain, and when Google redirects
# back, Streamlit can (and often does) start a brand-new session, wiping
# session_state clean. The `state` parameter Google echoes back in the
# redirect URL is the one thing that DOES reliably survive (it's just
# part of the URL), so we use it as the key to look the verifier back up
# from disk instead of from session_state.
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


def _render_oauth_setup():
    st.subheader("🔐 Google से चैनल जोड़ें")
    saved = _load_oauth_config()

    if saved.get("_source") == "env":
        st.success(
            "✅ Setup environment variables से load हुआ है — यह सबसे सुरक्षित तरीका है, "
            "दोबारा भरने की ज़रूरत नहीं पड़ेगी।"
        )
        return saved.get("client_id", ""), saved.get("client_secret", ""), saved.get("redirect_uri", "")

    if saved.get("_source") == "secrets":
        st.success(
            "✅ Setup Streamlit Secrets से load हुआ है — यह restart/redeploy/sleep के बाद भी "
            "सुरक्षित रहेगा, दोबारा भरने की ज़रूरत नहीं पड़ेगी।"
        )
        return saved.get("client_id", ""), saved.get("client_secret", ""), saved.get("redirect_uri", "")

    with st.expander("⚙️ एक बार का Setup (Client ID/Secret)", expanded=not saved):
        st.warning(
            "⚠️ यह form-वाला तरीका सिर्फ़ local/testing के लिए है — Streamlit Cloud पर यहाँ भरी हुई "
            "value हर restart/redeploy/sleep पर मिट जाएगी। स्थायी setup के लिए **Streamlit Cloud → "
            "Manage app → Settings → Secrets** में `[youtube_oauth]` के नीचे client_id, "
            "client_secret, redirect_uri डालें — फिर यह form अपने आप दिखना बंद हो जाएगा।"
        )
        st.caption(
            "Google Cloud Console से लिया Client ID/Secret यहाँ डालें। ⚠️ यह भी plain text में "
            f"`{OAUTH_CONFIG_PATH}` में save होता है — `.gitignore` में ज़रूर जोड़ें।"
        )
        client_id = st.text_input("Client ID", value=saved.get("client_id", ""), key="yt_client_id")
        client_secret = st.text_input("Client Secret", value=saved.get("client_secret", ""), type="password", key="yt_client_secret")
        redirect_uri = st.text_input(
            "Redirect URI (यही Cloud Console में 'Authorized redirect URIs' में डालें, हूबहू)",
            value=saved.get("redirect_uri", ""), key="yt_redirect_uri",
            placeholder="https://your-app.streamlit.app/",
        )
        if st.button("💾 Save Setup", key="yt_oauth_save_btn"):
            _save_oauth_config(client_id, client_secret, redirect_uri)
            st.success("✅ Save हो गया (ध्यान दें: यह अगले restart तक ही रहेगा, ऊपर की चेतावनी देखें)।")
            st.rerun()

    return saved.get("client_id", ""), saved.get("client_secret", ""), saved.get("redirect_uri", "")


def _get_credentials():
    if not _GOOGLE_LIBS_AVAILABLE:
        st.error(
            "⚠️ ज़रूरी libraries install नहीं हैं। Terminal में चलाएँ:\n\n"
            "`pip install google-auth-oauthlib google-api-python-client`"
        )
        return None

    client_id, client_secret, redirect_uri = _render_oauth_setup()
    if not (client_id and client_secret and redirect_uri):
        st.info("ℹ️ ऊपर Setup भरकर Save करें, फिर यहाँ Login का बटन दिखेगा।")
        return None

    if "yt_credentials_json" in st.session_state:
        try:
            return Credentials.from_authorized_user_info(json.loads(st.session_state["yt_credentials_json"]), SCOPES)
        except Exception:
            del st.session_state["yt_credentials_json"]

    query_params = st.query_params
    if "code" in query_params:
        code = query_params["code"]
        state = query_params.get("state")
        already_processed = st.session_state.get("yt_oauth_processed_code")
        if code == already_processed:
            # Streamlit re-ran the script with the same ?code= still in the
            # URL (this happens easily) - a Google auth code is single-use,
            # so re-submitting it fails with "invalid_grant: Bad Request".
            # We've already handled this exact code - just clear the URL.
            st.query_params.clear()
            st.rerun()
        try:
            # Look the verifier up from disk by `state`, NOT session_state -
            # clicking the Login link is a real navigation to Google and
            # back, which can (and often does) start a brand-new Streamlit
            # session, wiping session_state clean in between.
            code_verifier = _pop_pending_verifier(state) if state else None
            flow = _get_flow(client_id, client_secret, redirect_uri, code_verifier=code_verifier)
            flow.fetch_token(code=code)
            creds = flow.credentials
            st.session_state["yt_credentials_json"] = creds.to_json()
            st.session_state["yt_oauth_processed_code"] = code
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.session_state["yt_oauth_processed_code"] = code  # don't retry this dead code in a loop
            st.error(
                f"❌ Login fail हुआ: {e}\n\n"
                "अगर यह दोबारा हो, तो नीचे दोबारा Login बटन दबाकर एक बिल्कुल नई कोशिश करें "
                "(पुराना redirect link दोबारा खोलने या बैक-बटन इस्तेमाल करने से बचें - Google का code एक ही बार चलता है)।"
            )
            return None

    flow = _get_flow(client_id, client_secret, redirect_uri)
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline", include_granted_scopes="true")
    # Save this exact Flow's code_verifier to disk, keyed by `state` - this
    # is the PKCE fix, done in a way that survives the real redirect to
    # Google and back (see _save_pending_verifier's docstring note).
    _save_pending_verifier(state, flow.code_verifier)
    st.link_button("🔓 अपने YouTube चैनल से Login करें (Google)", auth_url)
    return None


# ---------------------------------------------------------------------------
# Data fetchers (real API calls)
# ---------------------------------------------------------------------------
def _fetch_channel_overview(youtube):
    resp = youtube.channels().list(part="statistics,snippet,contentDetails", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        return None
    ch = items[0]
    return {
        "title": ch["snippet"]["title"],
        "subscribers": int(ch["statistics"].get("subscriberCount", 0)),
        "total_views": int(ch["statistics"].get("viewCount", 0)),
        "video_count": int(ch["statistics"].get("videoCount", 0)),
    }


def _fetch_analytics_timeseries(yta, days=28):
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    resp = yta.reports().query(
        ids="channel==MINE",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics="views,estimatedMinutesWatched,likes,subscribersGained",
        dimensions="day",
        sort="day",
    ).execute()
    return resp.get("rows", []), resp.get("columnHeaders", [])


def _fetch_watch_hours_365d(yta):
    end = datetime.utcnow().date()
    start = end - timedelta(days=365)
    resp = yta.reports().query(
        ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
        metrics="estimatedMinutesWatched",
    ).execute()
    rows = resp.get("rows", [])
    minutes = rows[0][0] if rows else 0
    return minutes / 60.0


def _fetch_shorts_views_90d(yta):
    end = datetime.utcnow().date()
    start = end - timedelta(days=90)
    try:
        resp = yta.reports().query(
            ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
            metrics="views", dimensions="creatorContentType",
            filters="creatorContentType==SHORTS",
        ).execute()
        rows = resp.get("rows", [])
        return rows[0][1] if rows and len(rows[0]) > 1 else (rows[0][0] if rows else 0)
    except Exception:
        return None  # dimension not available on all accounts - handled gracefully in UI


def _fetch_top_videos(yta, youtube, days=28, limit=10):
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    resp = yta.reports().query(
        ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
        metrics="views,estimatedMinutesWatched,likes",
        dimensions="video", sort="-views", maxResults=limit,
    ).execute()
    rows = resp.get("rows", [])
    if not rows:
        return []
    video_ids = [r[0] for r in rows]
    titles = {}
    try:
        vresp = youtube.videos().list(part="snippet", id=",".join(video_ids)).execute()
        for v in vresp.get("items", []):
            titles[v["id"]] = v["snippet"]["title"]
    except Exception:
        pass
    return [
        {"video_id": r[0], "title": titles.get(r[0], r[0]), "views": r[1], "watch_minutes": r[2], "likes": r[3]}
        for r in rows
    ]


def _search_niche_trend(youtube, query, days=7, limit=15):
    published_after = (datetime.utcnow() - timedelta(days=days)).isoformat("T") + "Z"
    resp = youtube.search().list(
        part="snippet", q=query, type="video", order="viewCount",
        publishedAfter=published_after, maxResults=limit,
    ).execute()
    items = resp.get("items", [])
    video_ids = [i["id"]["videoId"] for i in items]
    stats = {}
    if video_ids:
        try:
            vresp = youtube.videos().list(part="statistics", id=",".join(video_ids)).execute()
            for v in vresp.get("items", []):
                stats[v["id"]] = int(v["statistics"].get("viewCount", 0))
        except Exception:
            pass
    results = []
    for i in items:
        vid = i["id"]["videoId"]
        results.append({
            "title": i["snippet"]["title"],
            "channel": i["snippet"]["channelTitle"],
            "views": stats.get(vid, None),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    results.sort(key=lambda r: r["views"] or 0, reverse=True)
    return results


# ---------------------------------------------------------------------------
# UI sections
# ---------------------------------------------------------------------------
def _render_monetization_tracker(subs, watch_hours, shorts_views, upload_count=None):
    st.subheader("🎯 Monetization Progress Tracker")
    st.caption("YouTube के वास्तविक (verified, जनवरी 2026) thresholds के मुकाबले आपकी असली स्थिति।")

    ea = YPP_THRESHOLDS["early_access"]
    fm = YPP_THRESHOLDS["full_monetization"]

    st.markdown("**Early Access Tier** (Super Thanks/Memberships/Shopping खुलेंगे)")
    c1, c2 = st.columns(2)
    with c1:
        st.progress(min(1.0, subs / ea["subs"]), text=f"Subscribers: {subs:,} / {ea['subs']:,}")
    with c2:
        wh_pct = min(1.0, watch_hours / ea["watch_hours_365d"]) if watch_hours else 0
        st.progress(wh_pct, text=f"Watch Hours (365 दिन): {watch_hours:,.0f} / {ea['watch_hours_365d']:,}")

    st.markdown("**Full Monetization Tier** (Ad Revenue खुलेगा)")
    c3, c4 = st.columns(2)
    with c3:
        st.progress(min(1.0, subs / fm["subs"]), text=f"Subscribers: {subs:,} / {fm['subs']:,}")
    with c4:
        wh_pct2 = min(1.0, watch_hours / fm["watch_hours_365d"]) if watch_hours else 0
        st.progress(wh_pct2, text=f"Watch Hours (365 दिन): {watch_hours:,.0f} / {fm['watch_hours_365d']:,}")

    if shorts_views is not None:
        st.caption(f"📱 Shorts Views (90 दिन): **{shorts_views:,}** / 3,000,000 (Early) / 10,000,000 (Full) — "
                   "Watch Hours और Shorts Views अलग-अलग रास्ते हैं, दोनों मिलते नहीं, कोई एक पूरा होना काफ़ी है।")
    else:
        st.caption("ℹ️ Shorts-views अलग से नहीं निकल पाया (यह metric सभी accounts पर उपलब्ध नहीं है) — "
                   "Watch Hours वाला रास्ता ऊपर देखें।")

    st.warning(
        "⚠️ **1 फ़रवरी 2027 से** Full Monetization के लिए ज़रूरी watch hours 4,000→8,000 और Shorts views "
        "10M→20M हो जाएँगे (subscribers की सीमा 1,000 ही रहेगी)। जल्दी apply करना फ़ायदेमंद रहेगा।"
    )


def _render_content_tips():
    with st.expander("💡 सामान्य Best-Practice सलाह (कोई गारंटी नहीं, सिर्फ़ सामान्य दिशा-निर्देश)"):
        st.markdown(
            "- पहले 15 सेकंड में hook मज़बूत रखें — retention यहीं तय होती है\n"
            "- Consistency ज़्यादा मायने रखती है एक बार के viral video से\n"
            "- Community Guidelines strikes से बचें — monetization सीधे रुक सकती है\n"
            "- Title/Thumbnail वही लिखें/बनाएँ जो content में सच में है — misleading clickbait "
            "engagement तो ला सकता है, पर retention गिरने से algorithm नुकसान भी कर सकता है\n"
            "- Shorts और Long-form दोनों साथ चलाना अक्सर subscriber growth तेज़ करता है"
        )


def render_dashboard_ui():
    st.title("📊 Business Dashboard")
    st.caption("YouTube की अपनी official API से असली data — कोई अनुमानित 'secret' दावा नहीं।")

    if not _GOOGLE_LIBS_AVAILABLE:
        st.error(
            "⚠️ ज़रूरी libraries install नहीं हैं। Terminal में चलाएँ:\n\n"
            "`pip install google-auth-oauthlib google-api-python-client`"
        )
        return

    creds = _get_credentials()
    if creds is None:
        return

    try:
        youtube = build("youtube", "v3", credentials=creds)
        yta = build("youtubeAnalytics", "v2", credentials=creds)
    except Exception as e:
        st.error(f"YouTube से जुड़ने में दिक्कत: {e}")
        return

    st.divider()
    try:
        overview = _fetch_channel_overview(youtube)
    except HttpError as e:
        st.error(f"चैनल जानकारी नहीं मिल पाई: {e}")
        return
    except Exception as e:
        st.error(f"चैनल जानकारी नहीं मिल पाई: {e}")
        return

    if overview is None:
        st.warning("कोई चैनल नहीं मिला इस Google account से जुड़ा हुआ।")
        return

    st.subheader(f"📺 {overview['title']}")
    oc1, oc2, oc3 = st.columns(3)
    oc1.metric("Subscribers", f"{overview['subscribers']:,}")
    oc2.metric("कुल Views", f"{overview['total_views']:,}")
    oc3.metric("कुल Videos", f"{overview['video_count']:,}")

    # नीचे के सेक्शन्स को business_report.py और topic_trend_analysis.py में
    # बिना दोबारा API कॉल किए पास करने के लिए यह वेरिएबल्स पहले से खाली
    # values के साथ बना रहे हैं - अगर कोई fetch बीच में fail हो जाए, तो
    # आगे के सेक्शन crash नहीं होंगे, बस उतना डेटा खाली दिखेगा।
    watch_hours = 0
    shorts_views = None
    rows, headers = [], []
    top_videos = []

    st.divider()
    try:
        watch_hours = _fetch_watch_hours_365d(yta)
        shorts_views = _fetch_shorts_views_90d(yta)
        _render_monetization_tracker(overview["subscribers"], watch_hours, shorts_views)
    except Exception as e:
        st.error(f"Monetization data लाने में दिक्कत: {e}")

    st.divider()
    st.subheader("📈 पिछले 28 दिन का ट्रेंड")
    try:
        rows, headers = _fetch_analytics_timeseries(yta, days=28)
        if rows:
            import pandas as pd
            col_names = [h["name"] for h in headers]
            df = pd.DataFrame(rows, columns=col_names).set_index("day")
            tc1, tc2 = st.columns(2)
            with tc1:
                st.caption("Views")
                st.line_chart(df["views"])
            with tc2:
                st.caption("Watch Time (मिनट)")
                st.line_chart(df["estimatedMinutesWatched"])
            tc3, tc4 = st.columns(2)
            with tc3:
                st.caption("Likes")
                st.line_chart(df["likes"])
            with tc4:
                st.caption("नए Subscribers")
                st.line_chart(df["subscribersGained"])
        else:
            st.caption("अभी पर्याप्त data नहीं है इस period के लिए।")
    except Exception as e:
        st.error(f"Trend data लाने में दिक्कत: {e}")

    st.divider()
    st.subheader("🏆 टॉप वीडियो (पिछले 28 दिन)")
    try:
        top_videos = _fetch_top_videos(yta, youtube, days=28)
        if top_videos:
            st.dataframe(
                [{"Title": v["title"], "Views": v["views"], "Watch Minutes": v["watch_minutes"], "Likes": v["likes"]} for v in top_videos],
                use_container_width=True, hide_index=True,
            )
        else:
            st.caption("इस period में कोई video data नहीं मिला।")
    except Exception as e:
        st.error(f"Top videos लाने में दिक्कत: {e}")

    # ------------------------------------------------------------------
    # 📈 व्यापार रिपोर्ट - जो कुछ ऊपर fetch हो चुका है (rows/headers/
    # top_videos/watch_hours/shorts_views) उसी को दोबारा इस्तेमाल करता
    # है, कोई नई API क्वोटा खर्च नहीं होती।
    # ------------------------------------------------------------------
    try:
        render_business_report(youtube, overview, rows, headers, top_videos, watch_hours, shorts_views)
    except Exception as e:
        st.error(f"व्यापार रिपोर्ट बनाने में दिक्कत: {e}")

    # ------------------------------------------------------------------
    # 🧭 टॉपिक/फॉर्मेट परफॉर्मेंस (आपके अपने वीडियो) - यह अपना डेटा खुद
    # fetch करता है (90-दिन, बटन दबाने पर), इसलिए यहाँ अलग से try/except
    # module के अंदर ही संभला हुआ है।
    # ------------------------------------------------------------------
    try:
        render_own_topic_performance(youtube, yta)
    except Exception as e:
        st.error(f"टॉपिक परफॉर्मेंस में दिक्कत: {e}")

    st.divider()
    try:
        render_niche_intelligence(youtube)
    except Exception as e:
        st.error(f"Niche Intelligence में दिक्कत: {e}")

    st.divider()
    _render_content_tips()

    st.divider()
    if st.button("🚪 Logout (इस Google account से)", key="dash_logout_btn"):
        if "yt_credentials_json" in st.session_state:
            del st.session_state["yt_credentials_json"]
        st.rerun()


if __name__ == "__main__":
    st.set_page_config(page_title="Business Dashboard", page_icon="📊", layout="wide")
    render_dashboard_ui()
