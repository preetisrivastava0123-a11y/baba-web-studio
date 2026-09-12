"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो (Baba Generative Web Studio)
==============================================================
इस वर्ज़न में जोड़ा गया है:
  १. st.session_state से पूरी स्टेट लॉक (रिफ्रेश/रीरन पर कुछ न खोए)
  २. लाइव डायनामिक नंबरिंग — नंबर बदलते ही फोटो तुरंत नई क्रम-स्थिति
     पर स्क्रीन पर खिसक (re-order) जाती है
  ३. बैकग्राउंड-म्यूज़िक चुनने का selectbox (पावन सितार / दिव्य शंख /
     महाकाल डमरू बीट्स)
  ४. सबटाइटल-स्टाइल कंट्रोलर: रंग (पीला/सफेद) + फॉन्ट-साइज़ स्लाइडर
  ५. MoviePy 2.x+ सही इम्पोर्ट सिंटैक्स

⚠️ ईमानदार तकनीकी नोट: Streamlit में माउस से "ड्रैग करके" फोटो खींचना
   नेटिव फीचर नहीं है। यहाँ जो "लाइव री-ऑर्डर" दिया गया है, वह नंबर
   ड्रॉपडाउन बदलते ही लिस्ट को दोबारा सॉर्ट करके स्क्रीन पर तुरंत नई
   जगह पर दिखा देता है — जो अनुभव में लगभग ड्रैग-ड्रॉप जैसा ही लगता
   है, पर तकनीकी रूप से "क्रम-चयन + इंस्टेंट रीरेंडर" है। असली
   माउस-ड्रैग चाहिए तो streamlit-sortables जैसा अलग कंपोनेंट जोड़ना
   होगा — वह अगला अपग्रेड हो सकता है।
==============================================================
"""

import os
import subprocess
import tempfile

import streamlit as st

# --------------------------------------------------------------
# 1) पेज की बुनियादी सेटिंग (Page Configuration)
# --------------------------------------------------------------
st.set_page_config(
    page_title="बाबा जनरेटिव वेब स्टूडियो",
    page_icon="🎬",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ⚠️ फिक्स: MoviePy 2.x+ का सही इम्पोर्ट सिंटैक्स
from moviepy import VideoFileClip

from engine import compile_cinematic_video


# --------------------------------------------------------------
# 1.1) Playwright का Chromium ब्राउज़र इंस्टॉल करना — सिर्फ़ एक बार
# --------------------------------------------------------------
@st.cache_resource
def _ensure_playwright_chromium_installed():
    """Playwright का हेडलेस Chromium ब्राउज़र इंस्टॉल करता है (अगर पहले से न हो)।"""
    try:
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode == 0:
            return True, None
        return False, (result.stderr or result.stdout or "अज्ञात त्रुटि (unknown error)")
    except Exception as install_error:
        return False, str(install_error)


# --------------------------------------------------------------
# 2) कस्टम डार्क-थीम स्टाइलिंग
# --------------------------------------------------------------
def apply_dark_theme():
    """पूरे पेज पर सुंदर डार्क थीम, रंग, फॉन्ट और बटन का लुक लगाता है।"""
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(160deg, #0d0d0d 0%, #1a1a2e 100%);
            color: #f5f5f5;
        }
        .main-title {
            text-align: center;
            font-size: 42px;
            font-weight: 800;
            background: -webkit-linear-gradient(45deg, #ffd700, #ff8c00);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0px;
        }
        .sub-title {
            text-align: center;
            color: #b0b0b0;
            font-size: 16px;
            margin-bottom: 30px;
        }
        .section-heading {
            color: #ffd700;
            font-size: 20px;
            font-weight: 700;
            margin-top: 25px;
            margin-bottom: 8px;
        }
        .order-badge {
            background: linear-gradient(90deg, #ffd700, #ff8c00);
            color: #0d0d0d;
            font-weight: 800;
            border-radius: 8px;
            padding: 4px 10px;
            display: inline-block;
            margin-bottom: 6px;
            font-size: 13px;
        }
        div.stButton > button:first-child {
            background: linear-gradient(90deg, #ff416c, #ff4b2b);
            color: white;
            font-size: 20px;
            font-weight: 800;
            padding: 15px 0px;
            border-radius: 12px;
            border: none;
            width: 100%;
            box-shadow: 0px 0px 20px rgba(255, 75, 43, 0.6);
            transition: 0.3s;
        }
        div.stButton > button:first-child:hover {
            transform: scale(1.02);
            box-shadow: 0px 0px 30px rgba(255, 75, 43, 0.9);
        }
        div.stDownloadButton > button:first-child {
            background: linear-gradient(90deg, #11998e, #38ef7d);
            color: #0d0d0d;
            font-size: 20px;
            font-weight: 800;
            padding: 15px 0px;
            border-radius: 12px;
            border: none;
            width: 100%;
            box-shadow: 0px 0px 20px rgba(56, 239, 125, 0.6);
            transition: 0.3s;
        }
        div.stDownloadButton > button:first-child:hover {
            transform: scale(1.02);
            box-shadow: 0px 0px 30px rgba(56, 239, 125, 0.9);
        }
        </style>
        """,
        unsafe_allow_html=True
    )


# --------------------------------------------------------------
# 3) हेडर सेक्शन
# --------------------------------------------------------------
def render_header():
    st.markdown('<div class="main-title">🎬 बाबा जनरेटिव वेब स्टूडियो</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">मंदिर की कहानियों को सिनेमैटिक वीडियो में बदलें</div>', unsafe_allow_html=True)
    st.divider()


# --------------------------------------------------------------
# 4) session_state की बुनियादी शुरुआत (Initialization)
# --------------------------------------------------------------
def _initialize_session_state():
    """
    सभी ज़रूरी वैल्यूज़ को session_state में पहले से सेट कर देता है,
    ताकि पेज रीरन (जो Streamlit में हर क्लिक पर होता है) होने पर भी
    यूज़र का लिखा/चुना हुआ कुछ भी गायब (reset) न हो।
    """
    default_values = {
        "story_script_text": "",
        "ticker_text_value": "",
        "video_format_choice": "📱 9:16 Shorts (कहानी के अनुसार)",
        "duration_choice_value": "5 मिनट",
        "quality_choice_value": "720p HD",
        "bg_music_choice": "पावन सितार 🎼",
        "subtitle_color_choice": "पीला (Gold)",
        "subtitle_font_size": 65,
        "media_order_map": {},   # फाइल के नाम -> यूज़र-चुनी क्रम-संख्या
    }
    for key, default_value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# --------------------------------------------------------------
# 5) मल्टी-फाइल अपलोड + लाइव डायनामिक नंबरिंग/सॉर्टिंग
# --------------------------------------------------------------
def render_media_ordering_section(uploaded_files):
    """
    हर अपलोड की गई फाइल के आगे एक क्रम-संख्या ड्रॉपडाउन दिखाता है।
    सारी क्रम-संख्याएँ st.session_state["media_order_map"] में
    (फाइल के नाम के आधार पर) सेव रहती हैं, इसलिए नंबर बदलते ही अगले
    ही रीरन में लिस्ट दोबारा सॉर्ट होकर तुरंत नई क्रम-स्थिति पर
    स्क्रीन पर दिख जाती है — यही "लाइव री-ऑर्डर" इफ़ेक्ट है।

    रिटर्न:
        list -> क्रम-संख्या के अनुसार सजी हुई फाइलों की लिस्ट
    """
    if not uploaded_files:
        return []

    total_files = len(uploaded_files)
    order_map = st.session_state["media_order_map"]

    st.markdown('<div class="section-heading">🔢 फाइलों का क्रम तय करें (लाइव)</div>', unsafe_allow_html=True)
    st.caption("नंबर बदलते ही नीचे फोटो अपनी नई जगह पर तुरंत खिसक जाएगी।")

    # पहले हर फाइल के लिए डिफ़ॉल्ट क्रम-संख्या सेट करना (अगर पहले से न हो)
    for file_index, media_file in enumerate(uploaded_files):
        if media_file.name not in order_map:
            order_map[media_file.name] = file_index + 1

    # ---- क्रम-संख्या के अनुसार फाइलों को *अभी* सॉर्ट करना (लाइव री-ऑर्डर) ----
    sorted_files = sorted(uploaded_files, key=lambda f: order_map.get(f.name, 999))

    preview_columns = st.columns(min(total_files, 4) or 1)

    for display_index, media_file in enumerate(sorted_files):
        column = preview_columns[display_index % len(preview_columns)]
        with column:
            st.markdown(
                f'<span class="order-badge">क्रम {display_index + 1}: {media_file.name[:12]}</span>',
                unsafe_allow_html=True
            )
            if media_file.type and media_file.type.startswith("image"):
                st.image(media_file, use_container_width=True)
            else:
                st.markdown("🎞️ *(वीडियो क्लिप)*")

            # ---- नंबर बदलते ही session_state अपडेट + तुरंत रीरन ----
            def _on_order_change(file_name=media_file.name, widget_key=f"order_select_{media_file.name}"):
                st.session_state["media_order_map"][file_name] = st.session_state[widget_key]

            st.selectbox(
                label="क्रम संख्या",
                options=list(range(1, total_files + 1)),
                index=order_map.get(media_file.name, display_index + 1) - 1,
                key=f"order_select_{media_file.name}",
                label_visibility="collapsed",
                on_change=_on_order_change,
            )

    # डुप्लीकेट नंबर की चेतावनी
    all_chosen_numbers = [order_map[f.name] for f in uploaded_files]
    if len(set(all_chosen_numbers)) != len(all_chosen_numbers):
        st.warning("⚠️ दो या अधिक फाइलों को एक ही क्रम-संख्या मिली है। कृपया हर फाइल को अलग नंबर दें।")

    return sorted_files


# --------------------------------------------------------------
# 6) इनपुट सेक्शन (यूज़र से सारी जानकारी लेना)
# --------------------------------------------------------------
def render_input_section():
    """यूज़र से मीडिया, स्क्रिप्ट, म्यूज़िक, सबटाइटल-स्टाइल, फॉर्मेट, ड्यूरेशन, क्वालिटी लेता है।"""

    st.info(
        "💡 निर्देश: शॉर्ट्स के लिए ३-५ फ़ाइलें डालें। लंबे वीडियो "
        "(५ से ६० मिनट) के लिए विज़ुअल्स अपने आप लूप होकर बार-बार रिपीट होंगे!"
    )

    # --- मंदिर की फोटो/वीडियो अपलोड करना ---
    st.markdown('<div class="section-heading">📤 मंदिर की फोटो / वीडियो अपलोड करें</div>', unsafe_allow_html=True)
    uploaded_media_list = st.file_uploader(
        label="यहाँ एक या कई फाइलें अपलोड करें (Image या Video)",
        type=["jpg", "jpeg", "png", "mp4", "mov"],
        accept_multiple_files=True,
        help="मंदिर की एक या कई तस्वीरें/क्लिप्स अपलोड करें, फिर नीचे उनका क्रम तय करें"
    )

    ordered_media_list = render_media_ordering_section(uploaded_media_list or [])

    if ordered_media_list and len(ordered_media_list) < 3:
        st.caption("ℹ️ सुझाव: बेहतर शॉर्ट्स के लिए कम से कम ३ फाइलें डालें।")
    elif ordered_media_list and len(ordered_media_list) > 5:
        st.caption("ℹ️ ध्यान दें: ५ से ज़्यादा फाइलें लंबे वीडियो के लिए ज़्यादा उपयुक्त हैं।")

    # --- कहानी / स्क्रिप्ट — session_state से जुड़ा हुआ (key=...) ---
    st.markdown('<div class="section-heading">📝 कहानी / स्क्रिप्ट लिखें</div>', unsafe_allow_html=True)
    st.text_area(
        label="अपनी कहानी या स्क्रिप्ट यहाँ पेस्ट करें",
        height=220,
        placeholder="उदाहरण: इस पवित्र मंदिर की स्थापना सैकड़ों वर्ष पहले हुई थी...",
        help="यह टेक्स्ट वीडियो की नैरेशन/कहानी के तौर पर इस्तेमाल होगा",
        key="story_script_text",
    )

    # --- न्यूज़ पट्टी / आउट्रो कमेंट ---
    st.markdown('<div class="section-heading">📰 न्यूज़ पट्टी / आउट्रो कमेंट का टेक्स्ट</div>', unsafe_allow_html=True)
    st.text_input(
        label="वीडियो के क्लाइमेक्स में क्या दिखे?",
        placeholder="उदाहरण: आज का विशेष संदेश | हर हर महादेव 🙏",
        help="यह टेक्स्ट वीडियो के अंतिम 5.5 सेकंड वाले क्लाइमेक्स सेक्शन में दिखेगा",
        key="ticker_text_value",
    )

    st.divider()

    # --- बैकग्राउंड म्यूज़िक चुनना ---
    st.markdown('<div class="section-heading">🎵 बैकग्राउंड म्यूज़िक चुनें</div>', unsafe_allow_html=True)
    st.selectbox(
        label="म्यूज़िक",
        options=["पावन सितार 🎼", "दिव्य शंख 🐚", "महाकाल डमरू बीट्स 🥁"],
        key="bg_music_choice",
        label_visibility="collapsed",
    )

    st.divider()

    # --- सबटाइटल स्टाइल कंट्रोलर ---
    st.markdown('<div class="section-heading">🎨 सबटाइटल स्टाइल</div>', unsafe_allow_html=True)
    subtitle_style_col1, subtitle_style_col2 = st.columns(2)
    with subtitle_style_col1:
        st.selectbox(
            label="सबटाइटल का रंग",
            options=["पीला (Gold)", "सफ़ेद (White)"],
            key="subtitle_color_choice",
        )
    with subtitle_style_col2:
        st.slider(
            label="फॉन्ट साइज़ (px)",
            min_value=50,
            max_value=90,
            key="subtitle_font_size",
        )

    st.divider()

    # --- वीडियो फॉर्मेट चुनना ---
    st.markdown('<div class="section-heading">🎞️ वीडियो फॉर्मेट चुनें</div>', unsafe_allow_html=True)
    st.radio(
        label="फॉर्मेट",
        options=["📱 9:16 Shorts (कहानी के अनुसार)", "🖥️ 16:9 Long Video"],
        horizontal=True,
        label_visibility="collapsed",
        key="video_format_choice",
    )
    is_long_video = st.session_state["video_format_choice"].startswith("🖥️")

    # --- Long Video ड्यूरेशन ---
    selected_duration_seconds = None
    if is_long_video:
        st.radio(
            label="⏱️ वीडियो की लंबाई चुनें",
            options=["5 मिनट", "30 मिनट", "1 घंटा"],
            horizontal=True,
            key="duration_choice_value",
        )
        duration_map_minutes = {"5 मिनट": 5, "30 मिनट": 30, "1 घंटा": 60}
        selected_duration_seconds = duration_map_minutes[st.session_state["duration_choice_value"]] * 60

    # --- क्वालिटी कंट्रोलर ---
    st.markdown('<div class="section-heading">🎚️ वीडियो क्वालिटी चुनें</div>', unsafe_allow_html=True)
    st.radio(
        label="क्वालिटी",
        options=["720p HD", "1080p Full HD"],
        horizontal=True,
        label_visibility="collapsed",
        key="quality_choice_value",
    )

    st.divider()

    generate_clicked = st.button("🚀 GENERATE CINEMATIC VIDEO", use_container_width=True)

    # रंग के हिंदी लेबल को हेक्स-कोड में बदलना (engine.py को यही चाहिए होगा)
    subtitle_color_hex = "#FFD700" if st.session_state["subtitle_color_choice"].startswith("पीला") else "#FFFFFF"

    user_inputs = {
        "ordered_media_files": ordered_media_list,
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
# 7) अपलोड की गई फाइलों को डिस्क पर अस्थायी रूप से सेव करना
# --------------------------------------------------------------
def _save_uploaded_file_to_temp(uploaded_file):
    file_extension = os.path.splitext(uploaded_file.name)[1]
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
    temp_file.write(uploaded_file.read())
    temp_file.close()
    return temp_file.name


def _save_all_ordered_files_to_temp(ordered_media_files):
    return [_save_uploaded_file_to_temp(media_file) for media_file in ordered_media_files]


# --------------------------------------------------------------
# 8) फाइनल वीडियो से एक थंबनेल (JPG) निकालना
# --------------------------------------------------------------
def _generate_thumbnail_from_video(video_path: str) -> str:
    thumbnail_path = os.path.join(tempfile.gettempdir(), "cinematic_thumbnail.jpg")
    with VideoFileClip(video_path) as video_clip:
        middle_timestamp = video_clip.duration / 2
        video_clip.save_frame(thumbnail_path, t=middle_timestamp)
    return thumbnail_path


# --------------------------------------------------------------
# 9) मुख्य फंक्शन (Main Entry Point)
# --------------------------------------------------------------
def main():
    _initialize_session_state()   # सबसे पहले session_state तैयार करना
    apply_dark_theme()
    render_header()

    playwright_ok, playwright_error = _ensure_playwright_chromium_installed()
    if not playwright_error is None and not playwright_ok:
        st.warning(f"⚠️ Playwright Chromium इंस्टॉल करते समय समस्या आई: {playwright_error}")

    inputs = render_input_section()

    if inputs["generate_clicked"]:

        if not inputs["ordered_media_files"] or not inputs["story_script"].strip():
            st.warning("⚠️ कृपया पहले फाइल अपलोड करें और कहानी लिखें।")
            return

        try:
            with st.spinner("🎥 आपका सिनेमैटिक वीडियो बन रहा है... कृपया प्रतीक्षा करें"):

                temp_media_paths = _save_all_ordered_files_to_temp(inputs["ordered_media_files"])

                output_dir = "generated_video"
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                output_video_path = os.path.join(output_dir, "final_cinematic_output.mp4")

                # ---- मुख्य कॉल: अब म्यूज़िक + सबटाइटल-स्टाइल भी भेजी जा रही है ----
                # ⚠️ नोट: engine.py को अगले चरण में bg_music/sub_color/sub_size
                # पैरामीटर स्वीकार करने के लिए अपडेट करना होगा।
                final_video_path = compile_cinematic_video(
                    user_media_list=temp_media_paths,
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
            with st.expander("🔍 पूरी तकनीकी जानकारी (Technical Details) देखें"):
                st.code(traceback.format_exc())
            return

        st.success("✅ आपका सिनेमैटिक वीडियो सफलतापूर्वक तैयार हो गया है!")
        st.video(final_video_path)

        with open(final_video_path, "rb") as video_file:
            video_bytes = video_file.read()
        with open(final_thumbnail_path, "rb") as thumbnail_file:
            thumbnail_bytes = thumbnail_file.read()

        st.download_button(
            label="📥 DOWNLOAD YOUR CINEMATIC VIDEO & THUMBNAIL",
            data=video_bytes,
            file_name="baba_cinematic_video.mp4",
            mime="video/mp4",
            use_container_width=True,
        )
        st.download_button(
            label="🖼️ डाउनलोड थंबनेल (Thumbnail JPG)",
            data=thumbnail_bytes,
            file_name="baba_cinematic_thumbnail.jpg",
            mime="image/jpeg",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
