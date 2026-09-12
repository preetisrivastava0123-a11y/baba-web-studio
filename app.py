"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो (Baba Generative Web Studio)
==============================================================
यह फाइल हमारी वेबसाइट का "मुख्य चेहरा" (Frontend / UI) है।
अब इसमें इनपुट लेने के साथ-साथ engine.py को बुलाकर असली
सिनेमैटिक वीडियो जनरेट करने और उसे डाउनलोड करवाने का पूरा
फ्लो भी जुड़ चुका है।
==============================================================
"""

import os
# क्लाउड सर्वर पर प्लेराइट के क्रोमियम ब्राउज़र को 1-क्लिक में ऑटोमैटिक इंस्टॉल करना
os.system("playwright install chromium")

import tempfile

import streamlit as st
from moviepy.editor import VideoFileClip

# --------------------------------------------------------------
# हमारे कोर वीडियो-कंपाइलर इंजन को इम्पोर्ट करना
# --------------------------------------------------------------
from engine import compile_cinematic_video


# --------------------------------------------------------------
# 1) पेज की बुनियादी सेटिंग (Page Configuration)
# --------------------------------------------------------------
st.set_page_config(
    page_title="बाबा जनरेटिव वेब स्टूडियो",
    page_icon="🎬",
    layout="centered",          # पेज को बीच में केंद्रित रखें
    initial_sidebar_state="collapsed"
)

# --------------------------------------------------------------
# 2) कस्टम डार्क-थीम स्टाइलिंग (CSS के ज़रिए)
#    ताकि पेज दिखने में प्रोफेशनल और सिनेमैटिक लगे
# --------------------------------------------------------------
def apply_dark_theme():
    """
    यह फंक्शन पूरे पेज पर एक सुंदर डार्क थीम लगाता है।
    रंग, फॉन्ट और बटन का लुक यहीं से नियंत्रित होता है।
    """
    st.markdown(
        """
        <style>
        /* पूरे ऐप का बैकग्राउंड डार्क करें */
        .stApp {
            background: linear-gradient(160deg, #0d0d0d 0%, #1a1a2e 100%);
            color: #f5f5f5;
        }

        /* मुख्य टाइटल को सुनहरा और आकर्षक बनाना */
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

        /* सेक्शन के हेडिंग को हाइलाइट करना */
        .section-heading {
            color: #ffd700;
            font-size: 20px;
            font-weight: 700;
            margin-top: 25px;
            margin-bottom: 8px;
        }

        /* बड़ा चमकीला GENERATE बटन */
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

        /* बड़ा चमकीला DOWNLOAD बटन (हरे रंग की चमक के साथ) */
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
# 3) हेडर सेक्शन (टाइटल और सबटाइटल दिखाना)
# --------------------------------------------------------------
def render_header():
    """पेज के ऊपर टाइटल और छोटा परिचय दिखाता है।"""
    st.markdown('<div class="main-title">🎬 बाबा जनरेटिव वेब स्टूडियो</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">मंदिर की कहानियों को सिनेमैटिक वीडियो में बदलें</div>', unsafe_allow_html=True)
    st.divider()


# --------------------------------------------------------------
# 4) इनपुट सेक्शन (यूज़र से सारी जानकारी लेना)
# --------------------------------------------------------------
def render_input_section():
    """
    यहाँ यूज़र से चार चीज़ें ली जाती हैं:
    - मीडिया फाइल (फोटो/वीडियो)
    - कहानी/स्क्रिप्ट
    - न्यूज़ पट्टी / आउट्रो का टेक्स्ट
    - जनरेट बटन

    यह फंक्शन एक dictionary (dict) लौटाता है जिसमें सारा
    यूज़र इनपुट होता है — ताकि आगे इंजन इसे आसानी से इस्तेमाल कर सके।
    """

    # --- 4.1) मंदिर की फोटो/वीडियो अपलोड करना ---
    st.markdown('<div class="section-heading">📤 मंदिर की फोटो / वीडियो अपलोड करें</div>', unsafe_allow_html=True)
    uploaded_media = st.file_uploader(
        label="यहाँ फाइल अपलोड करें (Image या Video)",
        type=["jpg", "jpeg", "png", "mp4", "mov"],
        accept_multiple_files=False,
        help="मंदिर की तस्वीर या छोटा वीडियो क्लिप अपलोड करें"
    )

    # --- 4.2) कहानी / स्क्रिप्ट लिखने का बड़ा बॉक्स ---
    st.markdown('<div class="section-heading">📝 कहानी / स्क्रिप्ट लिखें</div>', unsafe_allow_html=True)
    story_script = st.text_area(
        label="अपनी कहानी या स्क्रिप्ट यहाँ पेस्ट करें",
        height=220,
        placeholder="उदाहरण: इस पवित्र मंदिर की स्थापना सैकड़ों वर्ष पहले हुई थी...",
        help="यह टेक्स्ट वीडियो की नैरेशन/कहानी के तौर पर इस्तेमाल होगा"
    )

    # --- 4.3) नीचे चलने वाली न्यूज़ पट्टी / आउट्रो कमेंट ---
    st.markdown('<div class="section-heading">📰 न्यूज़ पट्टी / आउट्रो कमेंट का टेक्स्ट</div>', unsafe_allow_html=True)
    ticker_text = st.text_input(
        label="वीडियो के क्लाइमेक्स में क्या दिखे?",
        placeholder="उदाहरण: आज का विशेष संदेश | हर हर महादेव 🙏",
        help="यह टेक्स्ट वीडियो के अंतिम 5.5 सेकंड वाले क्लाइमेक्स सेक्शन में दिखेगा"
    )

    st.divider()

    # --- 4.4) बड़ा चमकीला जनरेट बटन ---
    generate_clicked = st.button("🚀 GENERATE CINEMATIC VIDEO", use_container_width=True)

    # सारा इनपुट एक जगह dictionary में इकट्ठा करना
    user_inputs = {
        "media_file": uploaded_media,
        "story_script": story_script,
        "ticker_text": ticker_text,
        "generate_clicked": generate_clicked,
    }
    return user_inputs


# --------------------------------------------------------------
# 5) अपलोड की गई फाइल को डिस्क पर अस्थायी रूप से सेव करना
# --------------------------------------------------------------
def _save_uploaded_file_to_temp(uploaded_file):
    """
    Streamlit का file_uploader फाइल को मेमोरी (bytes) में देता है,
    लेकिन engine.py को असली फाइल-पाथ चाहिए। इसलिए यहाँ उसे
    अस्थायी (temporary) फाइल के रूप में डिस्क पर सेव किया जाता है।

    रिटर्न:
        str -> अस्थायी फाइल की पूरी पाथ
    """
    file_extension = os.path.splitext(uploaded_file.name)[1]
    temp_file = tempfile.NamedTemporaryFile(
        delete=False, suffix=file_extension
    )
    temp_file.write(uploaded_file.read())
    temp_file.close()
    return temp_file.name


# --------------------------------------------------------------
# 6) फाइनल वीडियो से एक थंबनेल (JPG) निकालना
# --------------------------------------------------------------
def _generate_thumbnail_from_video(video_path: str) -> str:
    """
    फाइनल वीडियो के बीच वाले हिस्से से एक फ्रेम निकालकर उसे
    JPG थंबनेल के रूप में सेव करता है, ताकि यूज़र वीडियो के
    साथ-साथ एक थंबनेल भी डाउनलोड कर सके।

    रिटर्न:
        str -> थंबनेल JPG की फाइल-पाथ
    """
    thumbnail_path = os.path.join(
        tempfile.gettempdir(), "cinematic_thumbnail.jpg"
    )

    with VideoFileClip(video_path) as video_clip:
        # वीडियो के ठीक बीच वाले पल (moment) का फ्रेम निकालना
        middle_timestamp = video_clip.duration / 2
        video_clip.save_frame(thumbnail_path, t=middle_timestamp)

    return thumbnail_path


# --------------------------------------------------------------
# 7) मुख्य फंक्शन (Main Entry Point)
#    यही फंक्शन पूरे ऐप को चलाता है
# --------------------------------------------------------------
def main():
    apply_dark_theme()      # डार्क थीम लगाओ
    render_header()          # टाइटल दिखाओ
    inputs = render_input_section()   # सारा इनपुट लो

    # ------------------------------------------------------
    # जब यूज़र GENERATE बटन दबाए
    # ------------------------------------------------------
    if inputs["generate_clicked"]:

        # --- पहले बुनियादी जाँच (validation) करना ---
        if not inputs["media_file"] or not inputs["story_script"].strip():
            st.warning("⚠️ कृपया पहले फाइल अपलोड करें और कहानी लिखें।")
            return  # आगे कुछ भी न करें

        # --- लोडिंग स्पिनर दिखाते हुए असली वीडियो जनरेट करना ---
        with st.spinner("🎥 आपका सिनेमैटिक वीडियो बन रहा है... कृपया प्रतीक्षा करें (लगभग 40 सेकंड)"):

            # अपलोड की गई फाइल को अस्थायी पाथ पर सेव करना
            temp_media_path = _save_uploaded_file_to_temp(inputs["media_file"])

            # फाइनल आउटपुट वीडियो कहाँ सेव होगी, उसकी पाथ तय करना
            output_video_path = os.path.join(
                tempfile.gettempdir(), "final_cinematic_output.mp4"
            )

            # ---- यही वह मुख्य कॉल है जो सब कुछ जोड़ती है ----
            try:
                final_video_path = compile_cinematic_video(
                    user_media=temp_media_path,
                    script_text=inputs["story_script"],
                    outro_text=inputs["ticker_text"],
                    output_video_path=output_video_path,
                )

                # वीडियो से एक थंबनेल निकालना
                final_thumbnail_path = _generate_thumbnail_from_video(final_video_path)

            except Exception as error:
                # अगर इंजन में कहीं भी गड़बड़ी हो, तो यूज़र को साफ़ संदेश दिखाना
                st.error(f"❌ वीडियो बनाते समय एक त्रुटि आई: {error}")
                return

        # ------------------------------------------------------
        # वीडियो सफलतापूर्वक बनने के बाद: सफलता संदेश + डाउनलोड बटन
        # ------------------------------------------------------
        st.success("✅ आपका सिनेमैटिक वीडियो सफलतापूर्वक तैयार हो गया है!")

        # वीडियो को प्रीव्यू के तौर पर सीधे पेज पर भी दिखाना
        st.video(final_video_path)

        # वीडियो फाइल को बाइट्स (bytes) में पढ़ना (डाउनलोड बटन के लिए ज़रूरी)
        with open(final_video_path, "rb") as video_file:
            video_bytes = video_file.read()

        # थंबनेल फाइल को भी बाइट्स में पढ़ना
        with open(final_thumbnail_path, "rb") as thumbnail_file:
            thumbnail_bytes = thumbnail_file.read()

        # --- बड़ा, चमकीला वीडियो डाउनलोड बटन ---
        st.download_button(
            label="📥 DOWNLOAD YOUR CINEMATIC VIDEO & THUMBNAIL",
            data=video_bytes,
            file_name="baba_cinematic_video.mp4",
            mime="video/mp4",
            use_container_width=True,
        )

        # --- थंबनेल के लिए एक छोटा अतिरिक्त डाउनलोड बटन ---
        st.download_button(
            label="🖼️ डाउनलोड थंबनेल (Thumbnail JPG)",
            data=thumbnail_bytes,
            file_name="baba_cinematic_thumbnail.jpg",
            mime="image/jpeg",
            use_container_width=True,
        )


# --------------------------------------------------------------
# स्क्रिप्ट सीधे चलाने पर main() फंक्शन को कॉल करना
# --------------------------------------------------------------
if __name__ == "__main__":
    main()
