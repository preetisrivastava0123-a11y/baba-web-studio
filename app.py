"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो (Baba Generative Web Studio)
==============================================================
इस वर्ज़न में जोड़ा गया है — "इमेजिनेशन स्टूडियो" अपग्रेड:
  १. हर क्लिप के लिए टाइमलाइन कंट्रोल (Start Second → End Second)
  २. मल्टी-लेयर SFX टाइमलाइन (किस सेकंड पर कौन सी ध्वनि + कितनी आवाज़)
  ३. आलीशान ग्रिड-लेआउट: बाईं तरफ़ विज़ुअल-टाइमलाइन, दाईं तरफ़ ऑडियो-टाइमलाइन
  ४. सब कुछ st.session_state में पूरी तरह लॉक (रिफ्रेश पर कुछ न मिटे)
  ५. MoviePy 2.x+ सही इम्पोर्ट सिंटैक्स

⚠️ ईमानदार तकनीकी सीमा (ज़रूर पढ़ें):
   Streamlit में माउस से "खींचकर" (drag) टाइमलाइन-बार बनाना नेटिव
   फीचर नहीं है। यहाँ जो टाइमलाइन है, वह नंबर-इनपुट्स (Start/End
   सेकंड, Trigger सेकंड, Volume) पर आधारित है — इससे कंट्रोल पूरा
   मिलता है, पर विज़ुअल ड्रैग-बार नहीं। असली ड्रैग-बार चाहिए तो एक
   अलग JS-आधारित कंपोनेंट जोड़ना होगा (अगला संभावित अपग्रेड)।
==============================================================
"""

import os
import subprocess
import tempfile

import streamlit as st

# --------------------------------------------------------------
# 1) पेज की बुनियादी सेटिंग
# --------------------------------------------------------------
st.set_page_config(
    page_title="बाबा जनरेटिव वेब स्टूडियो",
    page_icon="🎬",
    layout="wide",              # ⚠️ बदलाव: ग्रिड-टाइमलाइन के लिए अब "wide" लेआउट
    initial_sidebar_state="collapsed"
)

from moviepy import VideoFileClip
from engine import compile_cinematic_video


# --------------------------------------------------------------
# 1.1) Playwright का Chromium ब्राउज़र इंस्टॉल करना — सिर्फ़ एक बार
# --------------------------------------------------------------
@st.cache_resource
def _ensure_playwright_chromium_installed():
    try:
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode == 0:
            return True, None
        return False, (result.stderr or result.stdout or "अज्ञात त्रुटि")
    except Exception as install_error:
        return False, str(install_error)


# --------------------------------------------------------------
# 2) डार्क-थीम + टाइमलाइन-कार्ड स्टाइलिंग
# --------------------------------------------------------------
def apply_dark_theme():
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(160deg, #0d0d0d 0%, #1a1a2e 100%);
            color: #f5f5f5;
        }
        .main-title {
            text-align: center; font-size: 42px; font-weight: 800;
            background: -webkit-linear-gradient(45deg, #ffd700, #ff8c00);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 0px;
        }
        .sub-title { text-align: center; color: #b0b0b0; font-size: 16px; margin-bottom: 20px; }
        .section-heading { color: #ffd700; font-size: 20px; font-weight: 700; margin-top: 20px; margin-bottom: 8px; }
        .timeline-card {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,215,0,0.25);
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 14px;
        }
        .order-badge {
            background: linear-gradient(90deg, #ffd700, #ff8c00);
            color: #0d0d0d; font-weight: 800; border-radius: 8px;
            padding: 4px 10px; display: inline-block; margin-bottom: 6px; font-size: 13px;
        }
        .sfx-badge {
            background: linear-gradient(90deg, #8e2de2, #4a00e0);
            color: #fff; font-weight: 700; border-radius: 8px;
            padding: 3px 9px; display: inline-block; font-size: 12px;
        }
        div.stButton > button:first-child {
            background: linear-gradient(90deg, #ff416c, #ff4b2b); color: white;
            font-size: 20px; font-weight: 800; padding: 15px 0px; border-radius: 12px;
            border: none; width: 100%; box-shadow: 0px 0px 20px rgba(255, 75, 43, 0.6); transition: 0.3s;
        }
        div.stButton > button:first-child:hover { transform: scale(1.02); box-shadow: 0px 0px 30px rgba(255, 75, 43, 0.9); }
        div.stDownloadButton > button:first-child {
            background: linear-gradient(90deg, #11998e, #38ef7d); color: #0d0d0d;
            font-size: 20px; font-weight: 800; padding: 15px 0px; border-radius: 12px;
            border: none; width: 100%; box-shadow: 0px 0px 20px rgba(56, 239, 125, 0.6); transition: 0.3s;
        }
        div.stDownloadButton > button:first-child:hover { transform: scale(1.02); box-shadow: 0px 0px 30px rgba(56, 239, 125, 0.9); }
        </style>
        """,
        unsafe_allow_html=True
    )


def render_header():
    st.markdown('<div class="main-title">🎬 बाबा जनरेटिव वेब स्टूडियो</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">मंदिर की कहानियों को सिनेमैटिक वीडियो में बदलें — प्रो टाइमलाइन एडिटर</div>', unsafe_allow_html=True)
    st.divider()


# --------------------------------------------------------------
# 3) session_state की शुरुआत
# --------------------------------------------------------------
def _initialize_session_state():
    default_values = {
        "story_script_text": "",
        "ticker_text_value": "",
        "video_format_choice": "📱 9:16 Shorts (कहानी के अनुसार)",
        "duration_choice_value": "5 मिनट",
        "quality_choice_value": "720p HD",
        "bg_music_choice": "पावन सितार 🎼",
        "subtitle_color_choice": "पीला (Gold)",
        "subtitle_font_size": 65,
        "media_order_map": {},      # फाइल-नाम -> क्रम-संख्या
        "media_time_map": {},       # फाइल-नाम -> {"start": x, "end": y}
        "sfx_events": [],           # [{"second": x, "type": "...", "volume": y}]
    }
    for key, default_value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# --------------------------------------------------------------
# 4) बाईं तरफ़: विज़ुअल-टाइमलाइन (क्रम + Start/End Second)
# --------------------------------------------------------------
def render_visual_timeline(uploaded_files):
    """
    हर अपलोड की गई फाइल के लिए तीन चीज़ें एक "टाइमलाइन-कार्ड" में
    दिखाता है: क्रम-संख्या, Start Second, End Second। तस्वीरों पर
    हमेशा Ken Burns ज़ूम अपने-आप लागू होगा (यह engine.py में पहले
    से तय लॉजिक है), इसलिए यहाँ सिर्फ़ ड्यूरेशन (start→end) चुनी जाती है।

    रिटर्न:
        list[dict] -> [{"file": UploadedFile, "order": int, "start": float, "end": float}, ...]
        क्रम-संख्या के अनुसार सजा हुआ
    """
    if not uploaded_files:
        st.info("⬅️ पहले ऊपर से फाइलें अपलोड करें, तब यहाँ टाइमलाइन दिखेगी।")
        return []

    order_map = st.session_state["media_order_map"]
    time_map = st.session_state["media_time_map"]
    total_files = len(uploaded_files)

    # डिफ़ॉल्ट क्रम व डिफ़ॉल्ट टाइमिंग सेट करना (सिर्फ़ पहली बार)
    for file_index, media_file in enumerate(uploaded_files):
        if media_file.name not in order_map:
            order_map[media_file.name] = file_index + 1
        if media_file.name not in time_map:
            time_map[media_file.name] = {"start": 0.0, "end": 5.0}

    sorted_files = sorted(uploaded_files, key=lambda f: order_map.get(f.name, 999))

    clip_settings_list = []

    for media_file in sorted_files:
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            preview_col, order_col, start_col, end_col = st.columns([2, 1, 1, 1])

            with preview_col:
                st.markdown(
                    f'<span class="order-badge">🎬 {media_file.name[:20]}</span>',
                    unsafe_allow_html=True
                )
                if media_file.type and media_file.type.startswith("image"):
                    st.image(media_file, use_container_width=True)
                else:
                    st.markdown("🎞️ *(वीडियो क्लिप — Ken Burns लागू नहीं होगा)*")

            with order_col:
                def _on_order_change(file_name=media_file.name, widget_key=f"order_{media_file.name}"):
                    st.session_state["media_order_map"][file_name] = st.session_state[widget_key]

                st.selectbox(
                    "क्रम", options=list(range(1, total_files + 1)),
                    index=order_map.get(media_file.name, 1) - 1,
                    key=f"order_{media_file.name}", on_change=_on_order_change,
                )

            with start_col:
                def _on_start_change(file_name=media_file.name, widget_key=f"start_{media_file.name}"):
                    st.session_state["media_time_map"][file_name]["start"] = st.session_state[widget_key]

                st.number_input(
                    "Start Second", min_value=0.0,
                    value=time_map[media_file.name]["start"],
                    step=0.5, key=f"start_{media_file.name}", on_change=_on_start_change,
                )

            with end_col:
                def _on_end_change(file_name=media_file.name, widget_key=f"end_{media_file.name}"):
                    st.session_state["media_time_map"][file_name]["end"] = st.session_state[widget_key]

                st.number_input(
                    "End Second", min_value=0.5,
                    value=time_map[media_file.name]["end"],
                    step=0.5, key=f"end_{media_file.name}", on_change=_on_end_change,
                )

            st.markdown('</div>', unsafe_allow_html=True)

        clip_settings_list.append({
            "file": media_file,
            "order": order_map[media_file.name],
            "start": time_map[media_file.name]["start"],
            "end": time_map[media_file.name]["end"],
        })

    # डुप्लीकेट-क्रम चेतावनी
    all_orders = [c["order"] for c in clip_settings_list]
    if len(set(all_orders)) != len(all_orders):
        st.warning("⚠️ दो या अधिक फाइलों को एक ही क्रम-संख्या मिली है।")

    # गलत Start/End चेतावनी
    for clip in clip_settings_list:
        if clip["end"] <= clip["start"]:
            st.warning(f"⚠️ '{clip['file'].name}' का End Second, Start Second से बड़ा होना चाहिए।")

    return sorted(clip_settings_list, key=lambda c: c["order"])


# --------------------------------------------------------------
# 5) दाईं तरफ़: मल्टी-लेयर SFX टाइमलाइन (जोड़ना/हटाना)
# --------------------------------------------------------------
def render_sfx_timeline():
    """
    यूज़र किसी भी सेकंड पर एक SFX-इवेंट जोड़ सकता है: कौन सी ध्वनि
    (शंखनाद / डमरू बीट्स / चिड़ियों की चहचहाहट), किस सेकंड पर बजेगी,
    और कितनी आवाज़ (0.0 से 1.0 वॉल्यूम) में। सभी इवेंट्स एक लिस्ट
    के रूप में session_state["sfx_events"] में लॉक रहते हैं।

    रिटर्न:
        list[dict] -> [{"second": float, "type": str, "volume": float}, ...]
    """
    st.markdown('<div class="section-heading">🔊 SFX टाइमलाइन (मल्टी-लेयर ऑडियो)</div>', unsafe_allow_html=True)
    st.caption("किसी भी सेकंड पर ध्वनि-इफ़ेक्ट ट्रिगर करें — जितने चाहें उतने जोड़ें।")

    sfx_type_options = ["शंखनाद 🐚", "डमरू बीट्स 🥁", "चिड़ियों की चहचहाहट 🐦"]

    # ---- मौजूदा SFX-इवेंट्स दिखाना (हर एक अपने कार्ड में) ----
    for event_index, sfx_event in enumerate(st.session_state["sfx_events"]):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            st.markdown(
                f'<span class="sfx-badge">🎯 इवेंट {event_index + 1}</span>',
                unsafe_allow_html=True
            )
            sfx_col1, sfx_col2, sfx_col3, sfx_col4 = st.columns([1, 2, 2, 1])

            with sfx_col1:
                st.markdown(f"**{sfx_event['second']}s**")
            with sfx_col2:
                st.markdown(f"🎵 {sfx_event['type']}")
            with sfx_col3:
                st.markdown(f"🔊 वॉल्यूम: {sfx_event['volume']}")
            with sfx_col4:
                if st.button("❌ हटाएँ", key=f"remove_sfx_{event_index}"):
                    st.session_state["sfx_events"].pop(event_index)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    # ---- नया SFX-इवेंट जोड़ने का फॉर्म ----
    st.markdown("**➕ नया SFX-इवेंट जोड़ें**")
    add_col1, add_col2, add_col3, add_col4 = st.columns([1, 2, 2, 1])
    with add_col1:
        new_sfx_second = st.number_input("किस सेकंड पर?", min_value=0.0, step=0.5, key="new_sfx_second")
    with add_col2:
        new_sfx_type = st.selectbox("कौन सी ध्वनि?", options=sfx_type_options, key="new_sfx_type")
    with add_col3:
        new_sfx_volume = st.slider("वॉल्यूम", min_value=0.0, max_value=1.0, value=0.7, step=0.05, key="new_sfx_volume")
    with add_col4:
        st.write("")  # स्पेसिंग के लिए
        if st.button("➕ जोड़ें", key="add_sfx_button"):
            st.session_state["sfx_events"].append({
                "second": new_sfx_second,
                "type": new_sfx_type,
                "volume": new_sfx_volume,
            })
            st.rerun()

    return st.session_state["sfx_events"]


# --------------------------------------------------------------
# 6) इनपुट सेक्शन — पूरा ग्रिड-लेआउट यहीं जुड़ता है
# --------------------------------------------------------------
def render_input_section():
    st.info(
        "💡 निर्देश: शॉर्ट्स के लिए ३-५ फ़ाइलें डालें। लंबे वीडियो के लिए "
        "विज़ुअल्स अपने आप लूप होंगे। नीचे हर क्लिप का Start/End सेकंड और "
        "SFX-टाइमलाइन अलग से सजाएँ।"
    )

    # --- फाइल अपलोड ---
    st.markdown('<div class="section-heading">📤 मंदिर की फोटो / वीडियो अपलोड करें</div>', unsafe_allow_html=True)
    uploaded_media_list = st.file_uploader(
        label="यहाँ एक या कई फाइलें अपलोड करें (Image या Video)",
        type=["jpg", "jpeg", "png", "mp4", "mov"],
        accept_multiple_files=True,
    )

    st.divider()

    # --- ग्रिड-लेआउट: बाईं तरफ़ विज़ुअल-टाइमलाइन, दाईं तरफ़ SFX-टाइमलाइन ---
    left_panel, right_panel = st.columns([1.3, 1])

    with left_panel:
        st.markdown('<div class="section-heading">🎞️ विज़ुअल टाइमलाइन (क्रम + Start/End)</div>', unsafe_allow_html=True)
        clip_settings_list = render_visual_timeline(uploaded_media_list or [])

    with right_panel:
        sfx_events_list = render_sfx_timeline()

    st.divider()

    # --- कहानी / स्क्रिप्ट ---
    st.markdown('<div class="section-heading">📝 कहानी / स्क्रिप्ट लिखें</div>', unsafe_allow_html=True)
    st.text_area(
        label="अपनी कहानी या स्क्रिप्ट यहाँ पेस्ट करें", height=180,
        placeholder="उदाहरण: इस पवित्र मंदिर की स्थापना सैकड़ों वर्ष पहले हुई थी...",
        key="story_script_text",
    )

    # --- आउट्रो टेक्स्ट ---
    st.markdown('<div class="section-heading">📰 न्यूज़ पट्टी / आउट्रो कमेंट</div>', unsafe_allow_html=True)
    st.text_input(
        label="वीडियो के क्लाइमेक्स में क्या दिखे?",
        placeholder="उदाहरण: आज का विशेष संदेश | हर हर महादेव 🙏",
        key="ticker_text_value",
    )

    st.divider()

    # --- म्यूज़िक + सबटाइटल-स्टाइल + फॉर्मेट + क्वालिटी ---
    settings_col1, settings_col2 = st.columns(2)

    with settings_col1:
        st.markdown('<div class="section-heading">🎵 मुख्य बैकग्राउंड म्यूज़िक</div>', unsafe_allow_html=True)
        st.selectbox(
            "म्यूज़िक", options=["पावन सितार 🎼", "दिव्य शंख 🐚", "महाकाल डमरू बीट्स 🥁"],
            key="bg_music_choice", label_visibility="collapsed",
        )

        st.markdown('<div class="section-heading">🎞️ वीडियो फॉर्मेट</div>', unsafe_allow_html=True)
        st.radio(
            "फॉर्मेट", options=["📱 9:16 Shorts (कहानी के अनुसार)", "🖥️ 16:9 Long Video"],
            horizontal=True, key="video_format_choice", label_visibility="collapsed",
        )
        is_long_video = st.session_state["video_format_choice"].startswith("🖥️")

        selected_duration_seconds = None
        if is_long_video:
            st.radio(
                "ड्यूरेशन", options=["5 मिनट", "30 मिनट", "1 घंटा"],
                horizontal=True, key="duration_choice_value",
            )
            duration_map_minutes = {"5 मिनट": 5, "30 मिनट": 30, "1 घंटा": 60}
            selected_duration_seconds = duration_map_minutes[st.session_state["duration_choice_value"]] * 60

    with settings_col2:
        st.markdown('<div class="section-heading">🎨 सबटाइटल स्टाइल</div>', unsafe_allow_html=True)
        st.selectbox("रंग", options=["पीला (Gold)", "सफ़ेद (White)"], key="subtitle_color_choice")
        st.slider("फॉन्ट साइज़ (px)", min_value=50, max_value=90, key="subtitle_font_size")

        st.markdown('<div class="section-heading">🎚️ वीडियो क्वालिटी</div>', unsafe_allow_html=True)
        st.radio(
            "क्वालिटी", options=["720p HD", "1080p Full HD"],
            horizontal=True, key="quality_choice_value", label_visibility="collapsed",
        )

    st.divider()
    generate_clicked = st.button("🚀 GENERATE CINEMATIC VIDEO", use_container_width=True)

    subtitle_color_hex = "#FFD700" if st.session_state["subtitle_color_choice"].startswith("पीला") else "#FFFFFF"

    user_inputs = {
        "clip_settings_list": clip_settings_list,   # [{"file", "order", "start", "end"}, ...]
        "sfx_events": sfx_events_list,               # [{"second", "type", "volume"}, ...]
        "story_script": st.session_state["story_script_text"],
        "ticker_text": st.session_state["ticker_text_value"],
        "aspect_ratio": "16:9" if is_long_video else "9:16",
        "duration_seconds": selected_duration_seconds,
        "quality": "1080p" if st.session_state["quality_choice_value"].startswith("1080p") else "720p",
        "bg_music": st.session_state["bg_music_choice"],
        "sub_color": subtitle_color_hex,
        "sub_size": st.session_state["subtitle_font_size"],
        "generate_clicked": generate_clicked,
    }
    return user_inputs


# --------------------------------------------------------------
# 7) फाइलों को डिस्क पर सेव करना (अब Start/End मेटाडेटा के साथ)
# --------------------------------------------------------------
def _save_clip_settings_to_temp(clip_settings_list):
    """
    हर क्लिप की फाइल को डिस्क पर सेव करता है और उसके साथ उसका
    Start/End Second भी जोड़कर लौटाता है — ताकि engine.py को
    सीधा वही डेटा मिल जाए जो टाइमलाइन में तय हुआ था।
    """
    resolved_clip_settings = []
    for clip in clip_settings_list:
        file_extension = os.path.splitext(clip["file"].name)[1]
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        temp_file.write(clip["file"].read())
        temp_file.close()

        resolved_clip_settings.append({
            "path": temp_file.name,
            "start": clip["start"],
            "end": clip["end"],
        })
    return resolved_clip_settings


def _generate_thumbnail_from_video(video_path: str) -> str:
    thumbnail_path = os.path.join(tempfile.gettempdir(), "cinematic_thumbnail.jpg")
    with VideoFileClip(video_path) as video_clip:
        middle_timestamp = video_clip.duration / 2
        video_clip.save_frame(thumbnail_path, t=middle_timestamp)
    return thumbnail_path


# --------------------------------------------------------------
# 8) मुख्य फंक्शन
# --------------------------------------------------------------
def main():
    _initialize_session_state()
    apply_dark_theme()
    render_header()

    playwright_ok, playwright_error = _ensure_playwright_chromium_installed()
    if not playwright_error is None and not playwright_ok:
        st.warning(f"⚠️ Playwright Chromium इंस्टॉल करते समय समस्या आई: {playwright_error}")

    inputs = render_input_section()

    if inputs["generate_clicked"]:

        if not inputs["clip_settings_list"] or not inputs["story_script"].strip():
            st.warning("⚠️ कृपया पहले फाइल अपलोड करें, टाइमलाइन सजाएँ और कहानी लिखें।")
            return

        try:
            with st.spinner("🎥 आपका सिनेमैटिक वीडियो बन रहा है... कृपया प्रतीक्षा करें"):

                resolved_clip_settings = _save_clip_settings_to_temp(inputs["clip_settings_list"])

                output_dir = "generated_video"
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                output_video_path = os.path.join(output_dir, "final_cinematic_output.mp4")

                # ---- मुख्य कॉल: अब टाइमलाइन + SFX-इवेंट्स भी भेजी जा रही हैं ----
                # ⚠️ नोट: engine.py को अगले चरण में clip_settings_list (हर क्लिप का
                # start/end) और sfx_events (हर SFX का second/type/volume) स्वीकार
                # करने के लिए अपडेट करना होगा — अभी तक यह सिर्फ़ फ्लैट पाथ-लिस्ट
                # लेता था।
                final_video_path = compile_cinematic_video(
                    clip_settings_list=resolved_clip_settings,
                    sfx_events=inputs["sfx_events"],
                    script_text=inputs["story_script"],
                    outro_text=inputs["ticker_text"],
                    output_video_path=output_video_path,
                    aspect_ratio=inputs["aspect_ratio"],
                    duration_seconds=inputs["duration_seconds"],
                    quality=inputs["quality"],
                    bg_music=inputs["bg_music"],
                    sub_color=inputs["sub_color"],
                    sub_size=inputs["sub_size"],
                )

                final_thumbnail_path = _generate_thumbnail_from_video(final_video_path)

        except Exception as error:
            st.error(f"❌ वीडियो बनाते समय एक त्रुटि आई: {error}")
            import traceback
            with st.expander("🔍 पूरी तकनीकी जानकारी देखें"):
                st.code(traceback.format_exc())
            return

        st.success("✅ आपका सिनेमैटिक वीडियो सफलतापूर्वक तैयार हो गया है!")
        st.video(final_video_path)

        with open(final_video_path, "rb") as video_file:
            video_bytes = video_file.read()
        with open(final_thumbnail_path, "rb") as thumbnail_file:
            thumbnail_bytes = thumbnail_file.read()

        st.download_button(
            "📥 DOWNLOAD YOUR CINEMATIC VIDEO & THUMBNAIL",
            data=video_bytes, file_name="baba_cinematic_video.mp4",
            mime="video/mp4", use_container_width=True,
        )
        st.download_button(
            "🖼️ डाउनलोड थंबनेल (Thumbnail JPG)",
            data=thumbnail_bytes, file_name="baba_cinematic_thumbnail.jpg",
            mime="image/jpeg", use_container_width=True,
        )


if __name__ == "__main__":
    main()
