"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो (Baba Generative Web Studio)
==============================================================
इस वर्ज़न में जोड़ा गया है — "हॉलीवुड-ग्रेड ऑटोमेशन स्टूडियो" अपग्रेड:
  १. विस्तृत यूज़र गाइड (ऊपर एक्सपैंडर-बॉक्स में)
  २. मल्टी-म्यूज़िक/भजन अपलोडर + क्रम-संख्या + वॉल्यूम + वॉइस-रिमूवर टॉगल
  ३. धार्मिक ग्रन्थ PDF अपलोडर -> कहानी बॉक्स में ऑटो-टेक्स्ट-फिल
  ४. वॉइसओवर स्विच: "बाबा एआई दिव्य आवाज़ (Edge-TTS)" या
     "अपनी रिकॉर्ड की हुई ऑडियो अपलोड करें (Custom Voice)"
  ५. सब कुछ st.session_state में पूरी तरह लॉक (रिफ्रेश पर कुछ न मिटे)

⚠️ ज़रूरी: requirements.txt में "pypdf" लाइब्रेरी ज़रूर जोड़ें,
   वरना PDF-टेक्स्ट-एक्सट्रैक्शन फीचर काम नहीं करेगा (नीचे इसे
   try/except से सुरक्षित रखा गया है, ताकि लाइब्रेरी न मिलने पर
   भी पूरा ऐप क्रैश न हो, सिर्फ़ यह एक फीचर बंद रहे)।

⚠️ ईमानदार तकनीकी सीमा (पहले जैसी ही, अब भी लागू):
   Streamlit में माउस से "खींचकर" टाइमलाइन-बार बनाना नेटिव फीचर
   नहीं है — यहाँ टाइमलाइन नंबर-इनपुट्स पर आधारित है। इसी तरह
   "वॉइस-रिमूवर" (Vocal Isolation) और असली "AI वॉइस-क्लोनिंग" भी
   अभी सिर्फ़ UI-टॉगल/अपलोड के रूप में तैयार हैं — भारी बैकएंड-मॉडल
   (Spleeter/Demucs/RVC) फ्री-होस्टिंग पर अलग से जोड़ना होगा, यह
   अगला संभावित इंजन-अपग्रेड है।
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
    layout="wide",
    initial_sidebar_state="collapsed"
)

from moviepy import VideoFileClip
from engine import compile_cinematic_video

# --------------------------------------------------------------
# 1.1) PDF-टेक्स्ट-एक्सट्रैक्शन लाइब्रेरी को सुरक्षित तरीके से इम्पोर्ट करना
# --------------------------------------------------------------
# ⚠️ फिक्स: अगर requirements.txt में "pypdf" न हो, तो import सीधे
# फेल होकर पूरा ऐप क्रैश कर देता। अब यह सिर्फ़ PDF-फीचर को बंद
# रखेगा, बाकी पूरा ऐप सामान्य रूप से चलता रहेगा।
try:
    from pypdf import PdfReader
    PDF_SUPPORT_AVAILABLE = True
except Exception:
    PDF_SUPPORT_AVAILABLE = False


# --------------------------------------------------------------
# 1.2) Playwright का Chromium ब्राउज़र इंस्टॉल करना — सिर्फ़ एक बार
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
        .music-badge {
            background: linear-gradient(90deg, #ff8c00, #ff416c);
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
# 2.1) विस्तृत यूज़र गाइड (एक्सपैंडर बॉक्स)
# --------------------------------------------------------------
def render_user_guide():
    """
    पेज के बिल्कुल ऊपर एक खुलने-बंद होने वाला डिब्बा दिखाता है, जिसमें
    यूज़र के लिए हर बड़े फीचर का १-१ लाइन का साफ़ निर्देश होता है।
    """
    with st.expander("🦚 बाबा स्टूडियो यूज़र गाइड (User Guide)", expanded=False):
        st.markdown(
            """
            **क) विज़ुअल्स की टाइमलाइन कैसे सेट करें:**
            हर फोटो/वीडियो के आगे *Start Second* और *End Second* में वह समय डालें
            जहाँ से जहाँ तक वह क्लिप वीडियो में दिखेगी; क्रम-नंबर से तय होगा कि
            कौन सी क्लिप पहले आएगी।

            **ख) ग्रन्थ की PDF से कथा ऑटो-एक्सट्रैक्ट कैसे करें:**
            कहानी बॉक्स के ऊपर दिए "📂 धार्मिक कथा PDF अपलोड करें" में अपनी PDF
            डालें — उसका पूरा टेक्स्ट अपने-आप नीचे कहानी बॉक्स में भर जाएगा,
            फिर चाहें तो उसे एडिट कर सकते हैं।

            **ग) कई भजन अपलोड करके नंबर कैसे तय करें:**
            "🎵 भजन/म्यूज़िक अपलोडर" में एक साथ कई MP3/MP4 फाइलें डालें, फिर हर
            एक के आगे क्रम-संख्या (1, 2, 3...) चुनें कि पहले कौन सा भजन बजेगा।

            **घ) अपनी रिकॉर्ड की हुई आवाज़ कैसे इस्तेमाल करें:**
            "वॉइसओवर सेक्शन" में "मेरी अपनी रिकॉर्ड की हुई आवाज़ (Custom Audio)"
            चुनें और अपनी MP3 फाइल अपलोड करें — यही आपकी कहानी की मुख्य आवाज़ बनेगी।
            """
        )


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
        "subtitle_color_choice": "पीला (Gold)",
        "subtitle_font_size": 65,
        "media_order_map": {},        # फाइल-नाम -> क्रम-संख्या (विज़ुअल्स)
        "media_time_map": {},         # फाइल-नाम -> {"start": x, "end": y}
        "sfx_events": [],             # [{"second": x, "type": "...", "volume": y}]
        "music_order_map": {},        # भजन फाइल-नाम -> क्रम-संख्या
        "music_settings_map": {},     # भजन फाइल-नाम -> {"instrumental_only": bool, "volume": float}
        "voiceover_mode": "🕉️ बाबा एआई दिव्य आवाज़ (Edge-TTS)",
        "pdf_extracted_once_flag": False,   # ताकि एक ही PDF को बार-बार दोबारा ऑटो-फिल न करे
    }
    for key, default_value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# --------------------------------------------------------------
# 4) बाईं तरफ़: विज़ुअल-टाइमलाइन (क्रम + Start/End Second)
# --------------------------------------------------------------
def render_visual_timeline(uploaded_files):
    """
    हर अपलोड की गई फाइल के लिए क्रम-संख्या, Start Second, End Second
    दिखाता है। रिटर्न: क्रम-संख्या के अनुसार सजी हुई सेटिंग्स-लिस्ट।
    """
    if not uploaded_files:
        st.info("⬅️ पहले ऊपर से फाइलें अपलोड करें, तब यहाँ टाइमलाइन दिखेगी।")
        return []

    order_map = st.session_state["media_order_map"]
    time_map = st.session_state["media_time_map"]
    total_files = len(uploaded_files)

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

    all_orders = [c["order"] for c in clip_settings_list]
    if len(set(all_orders)) != len(all_orders):
        st.warning("⚠️ दो या अधिक फाइलों को एक ही क्रम-संख्या मिली है।")

    for clip in clip_settings_list:
        if clip["end"] <= clip["start"]:
            st.warning(f"⚠️ '{clip['file'].name}' का End Second, Start Second से बड़ा होना चाहिए।")

    return sorted(clip_settings_list, key=lambda c: c["order"])


# --------------------------------------------------------------
# 5) दाईं तरफ़: मल्टी-लेयर SFX टाइमलाइन (जोड़ना/हटाना)
# --------------------------------------------------------------
def render_sfx_timeline():
    """किसी भी सेकंड पर ध्वनि-इफ़ेक्ट ट्रिगर करने के इवेंट्स — पहले जैसा ही।"""
    st.markdown('<div class="section-heading">🔊 SFX टाइमलाइन (मल्टी-लेयर ऑडियो)</div>', unsafe_allow_html=True)
    st.caption("किसी भी सेकंड पर ध्वनि-इफ़ेक्ट ट्रिगर करें — जितने चाहें उतने जोड़ें।")

    sfx_type_options = ["शंखनाद 🐚", "डमरू बीट्स 🥁", "चिड़ियों की चहचहाहट 🐦"]

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

    st.markdown("**➕ नया SFX-इवेंट जोड़ें**")
    add_col1, add_col2, add_col3, add_col4 = st.columns([1, 2, 2, 1])
    with add_col1:
        new_sfx_second = st.number_input("किस सेकंड पर?", min_value=0.0, step=0.5, key="new_sfx_second")
    with add_col2:
        new_sfx_type = st.selectbox("कौन सी ध्वनि?", options=sfx_type_options, key="new_sfx_type")
    with add_col3:
        new_sfx_volume = st.slider("वॉल्यूम", min_value=0.0, max_value=1.0, value=0.7, step=0.05, key="new_sfx_volume")
    with add_col4:
        st.write("")
        if st.button("➕ जोड़ें", key="add_sfx_button"):
            st.session_state["sfx_events"].append({
                "second": new_sfx_second, "type": new_sfx_type, "volume": new_sfx_volume,
            })
            st.rerun()

    return st.session_state["sfx_events"]


# --------------------------------------------------------------
# 6) मल्टी-म्यूज़िक/भजन अपलोडर + क्रम + वॉल्यूम + वॉइस-रिमूवर टॉगल
# --------------------------------------------------------------
def render_music_playlist_section():
    """
    यूज़र कई भजन (MP3/MP4) अपलोड कर सकता है। हर एक के लिए: क्रम-संख्या,
    "केवल इंस्ट्रूमेंटल" टॉगल (वॉइस-रिमूवर मोड), और अलग वॉल्यूम स्लाइडर।

    रिटर्न:
        list[dict] -> [{"file": UploadedFile, "order": int,
                         "instrumental_only": bool, "volume": float}, ...]
        क्रम-संख्या के अनुसार सजी हुई
    """
    st.markdown('<div class="section-heading">🎵 भजन / म्यूज़िक अपलोडर (मल्टी-प्लेलिस्ट)</div>', unsafe_allow_html=True)
    uploaded_music_files = st.file_uploader(
        label="एक या कई भजन/म्यूज़िक फाइलें अपलोड करें (MP3 या MP4)",
        type=["mp3", "mp4", "wav", "m4a"],
        accept_multiple_files=True,
        key="music_files_uploader",
        help="वीडियो/ऑडियो दोनों चलेंगे — बैकएंड पर सिर्फ़ ऑडियो निकाला जाएगा",
    )

    if not uploaded_music_files:
        st.caption("ℹ️ अभी कोई भजन अपलोड नहीं हुआ — डिफ़ॉल्ट सितार-संगीत इस्तेमाल होगा।")
        return []

    order_map = st.session_state["music_order_map"]
    settings_map = st.session_state["music_settings_map"]
    total_music_files = len(uploaded_music_files)

    for file_index, music_file in enumerate(uploaded_music_files):
        if music_file.name not in order_map:
            order_map[music_file.name] = file_index + 1
        if music_file.name not in settings_map:
            settings_map[music_file.name] = {"instrumental_only": False, "volume": 0.8}

    sorted_music_files = sorted(uploaded_music_files, key=lambda f: order_map.get(f.name, 999))
    music_settings_list = []

    for music_file in sorted_music_files:
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            name_col, order_col, mode_col, volume_col = st.columns([2, 1, 2, 1.5])

            with name_col:
                st.markdown(
                    f'<span class="music-badge">🎶 {music_file.name[:22]}</span>',
                    unsafe_allow_html=True
                )

            with order_col:
                def _on_music_order_change(file_name=music_file.name, widget_key=f"music_order_{music_file.name}"):
                    st.session_state["music_order_map"][file_name] = st.session_state[widget_key]

                st.selectbox(
                    "क्रम", options=list(range(1, total_music_files + 1)),
                    index=order_map.get(music_file.name, 1) - 1,
                    key=f"music_order_{music_file.name}", on_change=_on_music_order_change,
                )

            with mode_col:
                def _on_instrumental_toggle_change(file_name=music_file.name, widget_key=f"instrumental_{music_file.name}"):
                    st.session_state["music_settings_map"][file_name]["instrumental_only"] = st.session_state[widget_key]

                st.toggle(
                    "केवल इंस्ट्रूमेंटल (Vocal Remover Mode)",
                    value=settings_map[music_file.name]["instrumental_only"],
                    key=f"instrumental_{music_file.name}",
                    on_change=_on_instrumental_toggle_change,
                    help="ऑन करने पर गायक की आवाज़ हटाकर सिर्फ़ बैकग्राउंड म्यूज़िक बजाने की कोशिश होगी",
                )

            with volume_col:
                def _on_music_volume_change(file_name=music_file.name, widget_key=f"music_vol_{music_file.name}"):
                    st.session_state["music_settings_map"][file_name]["volume"] = st.session_state[widget_key]

                st.slider(
                    "वॉल्यूम", min_value=0.0, max_value=1.0,
                    value=settings_map[music_file.name]["volume"],
                    step=0.05, key=f"music_vol_{music_file.name}",
                    on_change=_on_music_volume_change,
                )

            st.markdown('</div>', unsafe_allow_html=True)

        music_settings_list.append({
            "file": music_file,
            "order": order_map[music_file.name],
            "instrumental_only": settings_map[music_file.name]["instrumental_only"],
            "volume": settings_map[music_file.name]["volume"],
        })

    all_music_orders = [m["order"] for m in music_settings_list]
    if len(set(all_music_orders)) != len(all_music_orders):
        st.warning("⚠️ दो या अधिक भजनों को एक ही क्रम-संख्या मिली है।")

    return sorted(music_settings_list, key=lambda m: m["order"])


# --------------------------------------------------------------
# 7) धार्मिक ग्रन्थ PDF अपलोडर -> टेक्स्ट ऑटो-एक्सट्रैक्शन
# --------------------------------------------------------------
def render_pdf_story_extractor():
    """
    यूज़र एक PDF अपलोड करता है, उसका पूरा टेक्स्ट निकालकर
    session_state["story_script_text"] में भर दिया जाता है, ताकि
    नीचे कहानी बॉक्स अपने-आप उस टेक्स्ट से भर जाए।
    """
    st.markdown('<div class="section-heading">📂 धार्मिक कथा / ग्रन्थ PDF अपलोड करें</div>', unsafe_allow_html=True)

    if not PDF_SUPPORT_AVAILABLE:
        st.warning(
            "⚠️ PDF-एक्सट्रैक्शन के लिए 'pypdf' लाइब्रेरी इंस्टॉल नहीं है। "
            "कृपया requirements.txt में 'pypdf' जोड़कर फिर से डिप्लॉय करें।"
        )
        return

    uploaded_pdf_file = st.file_uploader(
        label="कहानी/ग्रन्थ की PDF अपलोड करें (वैकल्पिक)",
        type=["pdf"],
        key="story_pdf_uploader",
        help="PDF अपलोड होते ही उसका टेक्स्ट अपने-आप नीचे कहानी बॉक्स में भर जाएगा",
    )

    if uploaded_pdf_file is not None:
        try:
            pdf_reader = PdfReader(uploaded_pdf_file)
            extracted_text_parts = [page.extract_text() or "" for page in pdf_reader.pages]
            extracted_full_text = "\n".join(extracted_text_parts).strip()

            if extracted_full_text:
                # सिर्फ़ तभी ऑटो-फिल करना जब यूज़र ने अभी-अभी यह PDF अपलोड की हो,
                # ताकि हर rerun पर मैनुअल-एडिट किया हुआ टेक्स्ट बार-बार ओवरराइट न हो
                if st.session_state.get("last_pdf_name") != uploaded_pdf_file.name:
                    st.session_state["story_script_text"] = extracted_full_text
                    st.session_state["last_pdf_name"] = uploaded_pdf_file.name
                    st.success("✅ PDF से कथा सफलतापूर्वक निकालकर नीचे कहानी बॉक्स में भर दी गई है।")
            else:
                st.warning("⚠️ इस PDF से कोई टेक्स्ट नहीं निकाला जा सका (शायद यह स्कैन की गई इमेज-PDF है)।")

        except Exception as pdf_error:
            st.warning(f"⚠️ PDF पढ़ने में समस्या आई: {pdf_error}")


# --------------------------------------------------------------
# 8) वॉइसओवर सेक्शन: AI आवाज़ बनाम कस्टम रिकॉर्डेड आवाज़
# --------------------------------------------------------------
def render_voiceover_section():
    """
    यूज़र चुनता है कि वॉइसओवर के लिए बाबा-एआई आवाज़ (Edge-TTS) चलेगी,
    या अपनी खुद की रिकॉर्ड की हुई ऑडियो फाइल इस्तेमाल होगी।

    रिटर्न:
        (voiceover_mode: str, custom_audio_file या None)
    """
    st.markdown('<div class="section-heading">🎙️ वॉइसओवर चुनें</div>', unsafe_allow_html=True)
    st.radio(
        label="वॉइसओवर मोड",
        options=[
            "🕉️ बाबा एआई दिव्य आवाज़ (Edge-TTS)",
            "🎤 मेरी अपनी रिकॉर्ड की हुई आवाज़ (Custom Audio Upload)",
        ],
        key="voiceover_mode",
        label_visibility="collapsed",
    )

    custom_audio_file = None
    if st.session_state["voiceover_mode"].startswith("🎤"):
        custom_audio_file = st.file_uploader(
            label="अपनी रिकॉर्ड की हुई ऑडियो फाइल अपलोड करें (MP3/WAV)",
            type=["mp3", "wav", "m4a"],
            key="custom_voice_uploader",
            help="यह ऑडियो सीधे वीडियो का मुख्य वॉइसओवर बन जाएगी — कहानी सिर्फ़ सबटाइटल के लिए इस्तेमाल होगी",
        )
        if custom_audio_file is None:
            st.warning("⚠️ कृपया अपनी रिकॉर्डेड ऑडियो फाइल अपलोड करें, वरना Generate बटन दबाने पर एरर आएगा।")

    return st.session_state["voiceover_mode"], custom_audio_file


# --------------------------------------------------------------
# 9) इनपुट सेक्शन — पूरा ग्रिड-लेआउट यहीं जुड़ता है
# --------------------------------------------------------------
def render_input_section():
    st.info(
        "💡 निर्देश: शॉर्ट्स के लिए ३-५ फ़ाइलें डालें। लंबे वीडियो के लिए "
        "विज़ुअल्स अपने आप लूप होंगे। नीचे हर क्लिप का Start/End सेकंड, "
        "भजन-प्लेलिस्ट और SFX-टाइमलाइन अलग से सजाएँ।"
    )

    # --- फाइल अपलोड (विज़ुअल्स) ---
    st.markdown('<div class="section-heading">📤 मंदिर की फोटो / वीडियो अपलोड करें</div>', unsafe_allow_html=True)
    uploaded_media_list = st.file_uploader(
        label="यहाँ एक या कई फाइलें अपलोड करें (Image या Video)",
        type=["jpg", "jpeg", "png", "mp4", "mov"],
        accept_multiple_files=True,
        key="visual_files_uploader",
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

    # --- मल्टी-म्यूज़िक/भजन प्लेलिस्ट सेक्शन ---
    music_settings_list = render_music_playlist_section()

    st.divider()

    # --- PDF एक्सट्रैक्टर (कहानी बॉक्स के ठीक ऊपर) ---
    render_pdf_story_extractor()

    st.markdown('<div class="section-heading">📝 कहानी / स्क्रिप्ट लिखें</div>', unsafe_allow_html=True)
    st.text_area(
        label="अपनी कहानी या स्क्रिप्ट यहाँ पेस्ट करें (या ऊपर PDF से ऑटो-फिल करें)", height=180,
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

    # --- वॉइसओवर सेक्शन (AI बनाम कस्टम) ---
    voiceover_mode, custom_audio_file = render_voiceover_section()

    st.divider()

    # --- सबटाइटल-स्टाइल + फॉर्मेट + क्वालिटी ---
    settings_col1, settings_col2 = st.columns(2)

    with settings_col1:
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
        "clip_settings_list": clip_settings_list,
        "sfx_events": sfx_events_list,
        "music_settings_list": music_settings_list,
        "story_script": st.session_state["story_script_text"],
        "ticker_text": st.session_state["ticker_text_value"],
        "aspect_ratio": "16:9" if is_long_video else "9:16",
        "duration_seconds": selected_duration_seconds,
        "quality": "1080p" if st.session_state["quality_choice_value"].startswith("1080p") else "720p",
        "sub_color": subtitle_color_hex,
        "sub_size": st.session_state["subtitle_font_size"],
        "voiceover_mode": "custom" if voiceover_mode.startswith("🎤") else "ai_tts",
        "custom_audio_file": custom_audio_file,
        "generate_clicked": generate_clicked,
    }
    return user_inputs


# --------------------------------------------------------------
# 10) फाइलों को डिस्क पर सेव करना
# --------------------------------------------------------------
def _save_uploaded_file_to_temp(uploaded_file):
    file_extension = os.path.splitext(uploaded_file.name)[1]
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
    temp_file.write(uploaded_file.read())
    temp_file.close()
    return temp_file.name


def _save_clip_settings_to_temp(clip_settings_list):
    resolved_clip_settings = []
    for clip in clip_settings_list:
        resolved_clip_settings.append({
            "path": _save_uploaded_file_to_temp(clip["file"]),
            "start": clip["start"],
            "end": clip["end"],
        })
    return resolved_clip_settings


def _save_music_settings_to_temp(music_settings_list):
    """हर भजन-फाइल को डिस्क पर सेव करता है, उसकी सेटिंग्स के साथ।"""
    resolved_music_settings = []
    for music in music_settings_list:
        resolved_music_settings.append({
            "path": _save_uploaded_file_to_temp(music["file"]),
            "instrumental_only": music["instrumental_only"],
            "volume": music["volume"],
        })
    return resolved_music_settings


def _generate_thumbnail_from_video(video_path: str) -> str:
    thumbnail_path = os.path.join(tempfile.gettempdir(), "cinematic_thumbnail.jpg")
    with VideoFileClip(video_path) as video_clip:
        middle_timestamp = video_clip.duration / 2
        video_clip.save_frame(thumbnail_path, t=middle_timestamp)
    return thumbnail_path


# --------------------------------------------------------------
# 11) मुख्य फंक्शन
# --------------------------------------------------------------
def main():
    _initialize_session_state()
    apply_dark_theme()
    render_header()
    render_user_guide()   # ⚠️ नया: पेज के ऊपर यूज़र-गाइड एक्सपैंडर

    playwright_ok, playwright_error = _ensure_playwright_chromium_installed()
    if not playwright_error is None and not playwright_ok:
        st.warning(f"⚠️ Playwright Chromium इंस्टॉल करते समय समस्या आई: {playwright_error}")

    inputs = render_input_section()

    if inputs["generate_clicked"]:

        # --- वैलिडेशन: विज़ुअल्स + कहानी ज़रूरी हैं ---
        if not inputs["clip_settings_list"] or not inputs["story_script"].strip():
            st.warning("⚠️ कृपया पहले फाइल अपलोड करें, टाइमलाइन सजाएँ और कहानी लिखें।")
            return

        # --- वैलिडेशन: कस्टम-वॉइस मोड चुना हो तो ऑडियो ज़रूर हो ---
        if inputs["voiceover_mode"] == "custom" and inputs["custom_audio_file"] is None:
            st.warning("⚠️ आपने 'कस्टम आवाज़' मोड चुना है, कृपया अपनी रिकॉर्डेड ऑडियो फाइल अपलोड करें।")
            return

        try:
            with st.spinner("🎥 आपका सिनेमैटिक वीडियो बन रहा है... कृपया प्रतीक्षा करें"):

                resolved_clip_settings = _save_clip_settings_to_temp(inputs["clip_settings_list"])
                resolved_music_settings = _save_music_settings_to_temp(inputs["music_settings_list"])

                resolved_custom_audio_path = None
                if inputs["custom_audio_file"] is not None:
                    resolved_custom_audio_path = _save_uploaded_file_to_temp(inputs["custom_audio_file"])

                output_dir = "generated_video"
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                output_video_path = os.path.join(output_dir, "final_cinematic_output.mp4")

                # ---- मुख्य कॉल: अब म्यूज़िक-प्लेलिस्ट + वॉइसओवर-मोड भी भेजी जा रही हैं ----
                # ⚠️ नोट: engine.py को अगले चरण में music_settings_list,
                # voiceover_mode और custom_audio_path स्वीकार करने के लिए
                # अपडेट करना होगा।
                final_video_path = compile_cinematic_video(
                    clip_settings_list=resolved_clip_settings,
                    sfx_events=inputs["sfx_events"],
                    music_settings_list=resolved_music_settings,
                    script_text=inputs["story_script"],
                    outro_text=inputs["ticker_text"],
                    output_video_path=output_video_path,
                    aspect_ratio=inputs["aspect_ratio"],
                    duration_seconds=inputs["duration_seconds"],
                    quality=inputs["quality"],
                    sub_color=inputs["sub_color"],
                    sub_size=inputs["sub_size"],
                    voiceover_mode=inputs["voiceover_mode"],
                    custom_audio_path=resolved_custom_audio_path,
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
