"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो (Baba Generative Web Studio)
==============================================================
यह फाइल हमारी वेबसाइट का "मुख्य चेहरा" (Frontend / UI) है।
इस वर्ज़न में जोड़ा गया है:
  १. मल्टी-फाइल अपलोड + क्रम (नंबरिंग) सेट करने का UI
  २. यूज़र के लिए संक्षिप्त हिंदी निर्देश बॉक्स
  ३. 9:16 Shorts / 16:9 Long Video चुनने का विकल्प + ड्यूरेशन
  ४. 720p / 1080p क्वालिटी कंट्रोलर
  ५. अपलोड की गई फाइलों का लाइव थंबनेल प्रीव्यू (ताकि क्रम तय
     करना आसान हो) + Shorts के लिए फाइल-काउंट पर स्मार्ट चेतावनी
==============================================================
"""

import os
import subprocess
import tempfile

import streamlit as st

# --------------------------------------------------------------
# 1) पेज की बुनियादी सेटिंग (Page Configuration)
# --------------------------------------------------------------
# ⚠️ यह नियम पहले जैसा ही बरकरार है: set_page_config() स्क्रिप्ट का
# सबसे पहला Streamlit-कमांड होना चाहिए, वरना पूरा ऐप क्रैश हो जाता है।
st.set_page_config(
    page_title="बाबा जनरेटिव वेब स्टूडियो",
    page_icon="🎬",
    layout="centered",          # पेज को बीच में केंद्रित रखें
    initial_sidebar_state="collapsed"
)

from moviepy import VideoFileClip

# --------------------------------------------------------------
# हमारे कोर वीडियो-कंपाइलर इंजन को इम्पोर्ट करना
# --------------------------------------------------------------
from engine import compile_cinematic_video


# --------------------------------------------------------------
# 1.1) Playwright का Chromium ब्राउज़र इंस्टॉल करना — सिर्फ़ एक बार
# --------------------------------------------------------------
@st.cache_resource
def _ensure_playwright_chromium_installed():
    """
    Playwright का हेडलेस Chromium ब्राउज़र इंस्टॉल करता है (अगर पहले
    से इंस्टॉल न हो)। यह फंक्शन कोई st.* कमांड कॉल नहीं करता।

    रिटर्न:
        (success: bool, error_message: str | None)
    """
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
# 2) कस्टम डार्क-थीम स्टाइलिंग (CSS के ज़रिए)
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

        /* फाइल-क्रम कार्ड (numbering) के लिए छोटा सा बैज-स्टाइल बॉक्स */
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
    """पेज के ऊपर टाइटल और छोटा परिचय दिखाता है।"""
    st.markdown('<div class="main-title">🎬 बाबा जनरेटिव वेब स्टूडियो</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">मंदिर की कहानियों को सिनेमैटिक वीडियो में बदलें</div>', unsafe_allow_html=True)
    st.divider()


# --------------------------------------------------------------
# 4) मल्टी-फाइल अपलोड + क्रम (नंबरिंग) सेट करना
# --------------------------------------------------------------
def render_media_ordering_section(uploaded_files):
    """
    यूज़र द्वारा अपलोड की गई सभी फाइलों को दिखाता है और हर फाइल के
    लिए एक ड्रॉपडाउन देता है, जिससे यूज़र तय कर सके कि वीडियो में
    कौन सी फाइल किस नंबर (क्रम) पर चलेगी — जैसे "क्लिप १, क्लिप २"।

    रिटर्न:
        list -> यूज़र द्वारा चुने गए क्रम के अनुसार सजी हुई फाइलों की लिस्ट
    """
    if not uploaded_files:
        return []

    total_files = len(uploaded_files)

    st.markdown('<div class="section-heading">🔢 फाइलों का क्रम तय करें</div>', unsafe_allow_html=True)
    st.caption("नीचे हर फाइल के सामने वह नंबर चुनें, जिस क्रम में वह वीडियो में दिखनी चाहिए।")

    # हर फाइल के लिए यूज़र से क्रम-संख्या पूछना (डिफ़ॉल्ट: जिस क्रम में अपलोड हुई उसी क्रम में)
    chosen_order_numbers = []
    preview_columns = st.columns(min(total_files, 4) or 1)

    for file_index, media_file in enumerate(uploaded_files):
        column = preview_columns[file_index % len(preview_columns)]
        with column:
            st.markdown(
                f'<span class="order-badge">फाइल: {media_file.name[:14]}</span>',
                unsafe_allow_html=True
            )
            # इमेज हो तो थंबनेल दिखाओ, वीडियो हो तो सिर्फ़ नाम/आइकन दिखाओ
            if media_file.type and media_file.type.startswith("image"):
                st.image(media_file, use_container_width=True)
            else:
                st.markdown("🎞️ *(वीडियो क्लिप)*")

            selected_order = st.selectbox(
                label="क्रम संख्या",
                options=list(range(1, total_files + 1)),
                index=file_index,
                key=f"order_select_{file_index}",
                label_visibility="collapsed",
            )
            chosen_order_numbers.append(selected_order)

    # अगर यूज़र ने गलती से दो फाइलों को एक ही नंबर दे दिया हो, तो साफ़ चेतावनी देना
    if len(set(chosen_order_numbers)) != len(chosen_order_numbers):
        st.warning("⚠️ दो या अधिक फाइलों को एक ही क्रम-संख्या मिली है। कृपया हर फाइल को अलग नंबर दें।")

    # क्रम-संख्या के हिसाब से फाइलों को सही सीक्वेंस में सजाना
    ordered_pairs = sorted(zip(chosen_order_numbers, uploaded_files), key=lambda pair: pair[0])
    ordered_files = [media_file for _, media_file in ordered_pairs]
    return ordered_files


# --------------------------------------------------------------
# 5) इनपुट सेक्शन (यूज़र से सारी जानकारी लेना)
# --------------------------------------------------------------
def render_input_section():
    """
    यूज़र से मीडिया, स्क्रिप्ट, आउट्रो-टेक्स्ट, फॉर्मेट, ड्यूरेशन और
    क्वालिटी लेता है। सारा इनपुट dictionary में लौटाया जाता है।
    """

    # --- 5.1) संक्षिप्त निर्देश बॉक्स ---
    st.info(
        "💡 निर्देश: शॉर्ट्स के लिए ३-५ फ़ाइलें डालें। लंबे वीडियो "
        "(५ से ६० मिनट) के लिए विज़ुअल्स अपने आप लूप होकर बार-बार रिपीट होंगे!"
    )

    # --- 5.2) मंदिर की फोटो/वीडियो अपलोड करना (मल्टी-अपलोड) ---
    st.markdown('<div class="section-heading">📤 मंदिर की फोटो / वीडियो अपलोड करें</div>', unsafe_allow_html=True)
    uploaded_media_list = st.file_uploader(
        label="यहाँ एक या कई फाइलें अपलोड करें (Image या Video)",
        type=["jpg", "jpeg", "png", "mp4", "mov"],
        accept_multiple_files=True,
        help="मंदिर की एक या कई तस्वीरें/क्लिप्स अपलोड करें, फिर नीचे उनका क्रम तय करें"
    )

    # क्रम सेट करने वाला सेक्शन — सिर्फ़ तभी दिखेगा जब फाइलें अपलोड हों
    ordered_media_list = render_media_ordering_section(uploaded_media_list or [])

    # शॉर्ट्स के लिए फाइल-काउंट को लेकर स्मार्ट सुझाव
    if ordered_media_list and len(ordered_media_list) < 3:
        st.caption("ℹ️ सुझाव: बेहतर शॉर्ट्स के लिए कम से कम ३ फाइलें डालें।")
    elif ordered_media_list and len(ordered_media_list) > 5:
        st.caption("ℹ️ ध्यान दें: ५ से ज़्यादा फाइलें लंबे वीडियो के लिए ज़्यादा उपयुक्त हैं।")

    # --- 5.3) कहानी / स्क्रिप्ट लिखने का बड़ा बॉक्स ---
    st.markdown('<div class="section-heading">📝 कहानी / स्क्रिप्ट लिखें</div>', unsafe_allow_html=True)
    story_script = st.text_area(
        label="अपनी कहानी या स्क्रिप्ट यहाँ पेस्ट करें",
        height=220,
        placeholder="उदाहरण: इस पवित्र मंदिर की स्थापना सैकड़ों वर्ष पहले हुई थी...",
        help="यह टेक्स्ट वीडियो की नैरेशन/कहानी के तौर पर इस्तेमाल होगा"
    )

    # --- 5.4) नीचे चलने वाली न्यूज़ पट्टी / आउट्रो कमेंट ---
    st.markdown('<div class="section-heading">📰 न्यूज़ पट्टी / आउट्रो कमेंट का टेक्स्ट</div>', unsafe_allow_html=True)
    ticker_text = st.text_input(
        label="वीडियो के क्लाइमेक्स में क्या दिखे?",
        placeholder="उदाहरण: आज का विशेष संदेश | हर हर महादेव 🙏",
        help="यह टेक्स्ट वीडियो के अंतिम 5.5 सेकंड वाले क्लाइमेक्स सेक्शन में दिखेगा"
    )

    st.divider()

    # --- 5.5) वीडियो फॉर्मेट चुनना: 9:16 Shorts या 16:9 Long Video ---
    st.markdown('<div class="section-heading">🎞️ वीडियो फॉर्मेट चुनें</div>', unsafe_allow_html=True)
    video_format_choice = st.radio(
        label="फॉर्मेट",
        options=["📱 9:16 Shorts (कहानी के अनुसार)", "🖥️ 16:9 Long Video"],
        horizontal=True,
        label_visibility="collapsed",
    )
    is_long_video = video_format_choice.startswith("🖥️")

    # --- 5.6) अगर Long Video चुना है, तो ड्यूरेशन पूछना ---
    selected_duration_seconds = None
    if is_long_video:
        duration_choice = st.radio(
            label="⏱️ वीडियो की लंबाई चुनें",
            options=["5 मिनट", "30 मिनट", "1 घंटा"],
            horizontal=True,
        )
        duration_map_minutes = {"5 मिनट": 5, "30 मिनट": 30, "1 घंटा": 60}
        selected_duration_seconds = duration_map_minutes[duration_choice] * 60

    # --- 5.7) क्वालिटी कंट्रोलर: 720p या 1080p ---
    st.markdown('<div class="section-heading">🎚️ वीडियो क्वालिटी चुनें</div>', unsafe_allow_html=True)
    quality_choice = st.radio(
        label="क्वालिटी",
        options=["720p HD", "1080p Full HD"],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.divider()

    # --- 5.8) बड़ा चमकीला जनरेट बटन ---
    generate_clicked = st.button("🚀 GENERATE CINEMATIC VIDEO", use_container_width=True)

    # सारा इनपुट एक जगह dictionary में इकट्ठा करना
    user_inputs = {
        "ordered_media_files": ordered_media_list,
        "story_script": story_script,
        "ticker_text": ticker_text,
        "aspect_ratio": "16:9" if is_long_video else "9:16",
        "duration_seconds": selected_duration_seconds,   # Shorts के लिए None रहेगा
        "quality": "1080p" if quality_choice.startswith("1080p") else "720p",
        "generate_clicked": generate_clicked,
    }
    return user_inputs


# --------------------------------------------------------------
# 6) अपलोड की गई फाइल को डिस्क पर अस्थायी रूप से सेव करना
# --------------------------------------------------------------
def _save_uploaded_file_to_temp(uploaded_file):
    """एक अपलोड की गई फाइल को अस्थायी (temporary) फाइल के रूप में डिस्क पर सेव करता है।"""
    file_extension = os.path.splitext(uploaded_file.name)[1]
    temp_file = tempfile.NamedTemporaryFile(
        delete=False, suffix=file_extension
    )
    temp_file.write(uploaded_file.read())
    temp_file.close()
    return temp_file.name


def _save_all_ordered_files_to_temp(ordered_media_files):
    """
    क्रम में सजाई गई सभी फाइलों को एक-एक करके डिस्क पर सेव करता है
    और उनके अस्थायी पाथ की लिस्ट लौटाता है (सही क्रम में)।
    """
    return [_save_uploaded_file_to_temp(media_file) for media_file in ordered_media_files]


# --------------------------------------------------------------
# 7) फाइनल वीडियो से एक थंबनेल (JPG) निकालना
# --------------------------------------------------------------
def _generate_thumbnail_from_video(video_path: str) -> str:
    """फाइनल वीडियो के बीच वाले हिस्से से एक फ्रेम निकालकर JPG थंबनेल बनाता है।"""
    thumbnail_path = os.path.join(
        tempfile.gettempdir(), "cinematic_thumbnail.jpg"
    )

    with VideoFileClip(video_path) as video_clip:
        middle_timestamp = video_clip.duration / 2
        video_clip.save_frame(thumbnail_path, t=middle_timestamp)

    return thumbnail_path


# --------------------------------------------------------------
# 8) मुख्य फंक्शन (Main Entry Point)
# --------------------------------------------------------------
def main():
    apply_dark_theme()
    render_header()

    playwright_ok, playwright_error = _ensure_playwright_chromium_installed()
    if not playwright_error is None and not playwright_ok:
        st.warning(
            f"⚠️ Playwright Chromium इंस्टॉल करते समय समस्या आई: {playwright_error}"
        )

    inputs = render_input_section()

    if inputs["generate_clicked"]:

        # --- पहले बुनियादी जाँच (validation) करना ---
        if not inputs["ordered_media_files"] or not inputs["story_script"].strip():
            st.warning("⚠️ कृपया पहले फाइल अपलोड करें और कहानी लिखें।")
            return

        try:
            with st.spinner("🎥 आपका सिनेमैटिक वीडियो बन रहा है... कृपया प्रतीक्षा करें"):

                # सभी क्रम में सजाई गई फाइलों को अस्थायी पाथ पर सेव करना
                temp_media_paths = _save_all_ordered_files_to_temp(inputs["ordered_media_files"])

                output_video_path = os.path.join(
                    tempfile.gettempdir(), "final_cinematic_output.mp4"
                )

                # ---- मुख्य कॉल: अब फॉर्मेट, ड्यूरेशन और क्वालिटी भी भेजी जा रही है ----
                # ⚠️ नोट: engine.py को अगले चरण में अपडेट करना होगा ताकि यह
                # aspect_ratio / duration_seconds / quality और मल्टीपल
                # फाइलों (list) को सही से इस्तेमाल कर सके।
                final_video_path = compile_cinematic_video(
                    user_media=temp_media_paths,
                    script_text=inputs["story_script"],
                    outro_text=inputs["ticker_text"],
                    output_video_path=output_video_path,
                    aspect_ratio=inputs["aspect_ratio"],
                    duration_seconds=inputs["duration_seconds"],
                    quality=inputs["quality"],
                )

                final_thumbnail_path = _generate_thumbnail_from_video(final_video_path)

        except Exception as error:
            st.error(f"❌ वीडियो बनाते समय एक त्रुटि आई: {error}")
            import traceback
            with st.expander("🔍 पूरी तकनीकी जानकारी (Technical Details) देखें"):
                st.code(traceback.format_exc())
            return

        # ------------------------------------------------------
        # वीडियो सफलतापूर्वक बनने के बाद
        # ------------------------------------------------------
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
