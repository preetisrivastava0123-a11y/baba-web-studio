# ==============================================================================
# 📖 बाबा वेब स्टूडियो: A to Z मास्टर ब्लूप्रिंट UI (app.py)
# ==============================================================================
import os
import streamlit as st

# ------------------------------------------------------------------------------
# 1) पेज कॉन्फ़िगरेशन एवं CSS एस्थेटिक्स
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="बाबा वेब स्टूडियो — Master Studio Console",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Styling to Match High-Precision Studio Theme
st.markdown("""
<style>
    .stApp { background-color: #0b0f19; color: #f1f5f9; }
    .main-header {
        text-align: center;
        font-size: 36px;
        font-weight: 900;
        background: linear-gradient(90deg, #ff7e5f, #feb47b, #00f2fe);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2px;
    }
    .sub-header { text-align: center; color: #94a3b8; font-size: 14px; margin-bottom: 25px; }
    
    .track-card {
        background: #111827;
        border: 1px solid #1f2937;
        border-left: 5px solid #00f2fe;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 25px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    .track-card-mandatory { border-left: 5px solid #ef4444 !important; }
    .track-title { font-size: 20px; font-weight: 800; color: #38bdf8; margin-bottom: 8px; }
    .guideline-box {
        background: #1e293b;
        border-left: 3px solid #fbbf24;
        padding: 10px;
        border-radius: 6px;
        font-size: 13px;
        color: #cbd5e1;
        margin-bottom: 15px;
    }
    .empty-state {
        background: #0f172a;
        border: 1px dashed #334155;
        padding: 15px;
        text-align: center;
        border-radius: 8px;
        color: #64748b;
        font-size: 14px;
    }
    .mandatory-badge {
        background: #dc2626; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;
    }
    .optional-badge {
        background: #475569; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Document Extraction Engine Check
try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
except Exception:
    PDF_SUPPORT = False

try:
    import docx as docx_lib
    DOCX_SUPPORT = True
except Exception:
    DOCX_SUPPORT = False

# ------------------------------------------------------------------------------
# 2) Session State Init
# ------------------------------------------------------------------------------
if "visual_files" not in st.session_state: st.session_state["visual_files"] = []
if "video_timeline_slots" not in st.session_state: st.session_state["video_timeline_slots"] = []
if "audio_files" not in st.session_state: st.session_state["audio_files"] = []
if "music_timeline_slots" not in st.session_state: st.session_state["music_timeline_slots"] = []
if "sfx_events" not in st.session_state: st.session_state["sfx_events"] = []
if "story_script" not in st.session_state: st.session_state["story_script"] = ""
if "ticker_text" not in st.session_state: st.session_state["ticker_text"] = ""

# ------------------------------------------------------------------------------
# HEADER & USER ONBOARDING BLUEPRINT
# ------------------------------------------------------------------------------
st.markdown('<div class="main-header">📖 बाबा वेब स्टूडियो — Master Studio Console</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">उच्च-सटीकता (High-Precision) एवं स्वचालित (Auto-Magic) पौराणिक/आध्यात्मिक वीडियो इंजन</div>', unsafe_allow_html=True)

with st.expander("💡 प्रयोग मार्गदर्शिका (User Onboarding Guide) — पढ़ें", expanded=False):
    st.markdown("""
    **जय श्री राम! "बाबा वेब स्टूडियो" में आपका स्वागत है।**
    * **Step 0:** वीडियो का Format (9:16 Shorts या 16:9 Long Video) चुनें।
    * **Track 1 & 3 (अनिवार्य):** अपनी फोटो/वीडियो और मुख्य भजन/ऑडियो अपलोड करें।
    * **Track 6:** कथा/मंत्र का टेक्स्ट दें, AI Voice अपने आप बैकग्राउंड म्यूज़िक धीमा (Auto-Ducking) करके बोलेगी।
    * **Track 4 & 7:** अपनी पसंद के साउंड इफ़ेक्ट्स (शंख, डमरू) और म्यूज़िक मोड्स चुनें।
    * **Climax Engine:** अंत के 10-15 सेकंड में स्पार्क्स, फ़्लोटिंग बैलून्स और 3D LIKE & SUBSCRIBE बटन्स जुड़ेंगे।
    """)

# ------------------------------------------------------------------------------
# ⚙️ STEP 0: मास्टर सेटअप बॉक्स (Master Setup)
# ------------------------------------------------------------------------------
st.markdown('<div class="track-card"><div class="track-title">⚙️ Step 0: मास्टर सेटअप बॉक्स (Master Setup)</div>', unsafe_allow_html=True)
c_set1, c_set2, c_set3 = st.columns(3)

with c_set1:
    video_format = st.radio("1. वीडियो फॉर्मेट", ["📱 9:16 Shorts (Default)", "📺 16:9 Long Video"], help="Shorts या Long Video चुनें")

with c_set2:
    if "Shorts" in video_format:
        duration_mode = st.selectbox("2. ड्यूरेशन एवं स्मार्ट क्लाइमेक्स", ["30 Sec (20s Content + 10s Climax)", "15 Sec (Custom)", "45 Sec (Custom)"])
    else:
        duration_mode = st.selectbox("2. ड्यूरेशन एवं स्मार्ट क्लाइमेक्स", ["5 मिनट (15s Climax)", "10 मिनट", "30 मिनट", "60 मिनट", "कस्टम टाइम"])

with c_set3:
    video_quality = st.radio("3. वीडियो क्वालिटी", ["🔘 720p HD (तेज़ प्रोसेसिंग)", "🔘 1080p Full HD (Default) (क्रिस्प)"], index=1)
st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 🖼️ TRACK 1: वीडियो क्रिएशन फोल्डर (Visuals Layer) — [MANDATORY]
# ------------------------------------------------------------------------------
st.markdown('<div class="track-card track-card-mandatory"><div class="track-title">🖼️ Track 1: वीडियो क्रिएशन फोल्डर (Visuals Layer) <span class="mandatory-badge">MANDATORY</span></div>', unsafe_allow_html=True)
st.markdown("""
<div class="guideline-box">
<b>📌 गाइडलाइन:</b><br>
- <b>Shorts (9:16):</b> न्यूनतम 2-3, अधिकतम 8-10 फाइल्स (60 सेकंड की सीमा हेतु)।<br>
- <b>Long Video (16:9):</b> न्यूनतम 3 फाइल्स, आवश्यकतानुसार अधिकतम फाइल्स।
</div>
""", unsafe_allow_html=True)

uploaded_visuals = st.file_uploader("JPG/PNG इमेजेस एवं MP4/MOV वीडियो का बल्क अपलोड करें", type=["jpg", "png", "jpeg", "mp4", "mov"], accept_multiple_files=True, key="tr1_up")

if uploaded_visuals:
    st.session_state["visual_files"] = uploaded_visuals

if not st.session_state["visual_files"]:
    st.markdown('<div class="empty-state">📂 कृपया वीडियो शुरू करने के लिए अपनी इमेज या वीडियो फाइलें यहाँ अपलोड करें।</div>', unsafe_allow_html=True)
else:
    st.subheader("📋 री-ऑर्डरिंग और सीक्वेंसिंग टेबल")
    total_visual_time = 0.0
    
    for idx, f in enumerate(st.session_state["visual_files"]):
        is_vid = f.name.lower().endswith(('.mp4', '.mov'))
        c_tr1_1, c_tr1_2, c_tr1_3, c_tr1_4, c_tr1_5 = st.columns([1, 3, 2, 2, 2])
        
        with c_tr1_1:
            st.write(f"**#{idx+1}**")
        with c_tr1_2:
            st.caption(f"{'🎞️ Video' if is_vid else '🖼️ Image'}: {f.name[:18]}")
        with c_tr1_3:
            order_no = st.number_input("Order", min_value=1, value=idx+1, key=f"tr1_ord_{idx}")
        with c_tr1_4:
            st_sec = st.number_input("Start Sec", min_value=0.0, value=0.0, key=f"tr1_st_{idx}")
        with c_tr1_5:
            end_sec = st.number_input("End Sec", min_value=1.0, value=5.0, key=f"tr1_end_{idx}")
            total_visual_time += (end_sec - st_sec)

    c_eff1, c_eff2 = st.columns(2)
    with c_eff1:
        ken_burns = st.checkbox("🔍 Ken Burns ज़ूम/मोशन इफ़ेक्ट लागू करें", value=True)
    with c_eff2:
        st.info(f"⏱️ **Total Visual Time:** {total_visual_time:.1f} Seconds")
        
st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 🎬 TRACK 2: वीडियो क्लिप्स टाइमलाइन — [OPTIONAL / SKIPPABLE]
# ------------------------------------------------------------------------------
st.markdown('<div class="track-card"><div class="track-title">🎬 Track 2: वीडियो क्लिप्स टाइमलाइन <span class="optional-badge">OPTIONAL</span></div>', unsafe_allow_html=True)
st.markdown('<div class="guideline-box">📌 मुख्य कहानी के बीच-बीच में मीम्स, इंट्रो या साइड वीडियो क्लिप्स जोड़ने और उनका समय तय करने के लिए।</div>', unsafe_allow_html=True)

if st.button("➕ नया वीडियो क्लिप टाइमलाइन पर जोड़ें", key="tr2_add"):
    st.session_state["video_timeline_slots"].append({"id": len(st.session_state["video_timeline_slots"])+1})
    st.rerun()

if not st.session_state["video_timeline_slots"]:
    st.markdown('<div class="empty-state">ℹ️ अभी कोई वीडियो-क्लिप टाइमलाइन स्लॉट नहीं जोड़ा गया।</div>', unsafe_allow_html=True)
else:
    for idx, slot in enumerate(st.session_state["video_timeline_slots"]):
        c_t2_1, c_t2_2, c_t2_3, c_t2_4, c_t2_5 = st.columns([3, 1.5, 1.5, 1.5, 0.5])
        with c_t2_1:
            st.file_uploader(f"क्लिप #{idx+1} MP4", type=["mp4", "mov"], key=f"tr2_file_{idx}")
        with c_t2_2:
            st.number_input("Order", min_value=1, value=idx+1, key=f"tr2_ord_{idx}")
        with c_t2_3:
            st.number_input("Start Sec", min_value=0.0, key=f"tr2_st_{idx}")
        with c_t2_4:
            st.number_input("End Sec", min_value=1.0, value=5.0, key=f"tr2_end_{idx}")
        with c_t2_5:
            if st.button("❌", key=f"tr2_del_{idx}"):
                st.session_state["video_timeline_slots"].pop(idx)
                st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 🎵 TRACK 3: मुख्य ऑडियो/म्यूज़िक लेयर — [MANDATORY]
# ------------------------------------------------------------------------------
st.markdown('<div class="track-card track-card-mandatory"><div class="track-title">🎵 Track 3: मुख्य ऑडियो/म्यूज़िक लेयर <span class="mandatory-badge">MANDATORY</span></div>', unsafe_allow_html=True)
st.markdown('<div class="guideline-box">📌 मुख्य बैकग्राउंड गाना/भजन यहाँ अपलोड करें। छोटा म्यूज़िक ऑटो-लूप होकर अंत तक चलेगा।</div>', unsafe_allow_html=True)

audio_ups = st.file_uploader("MP3/WAV मुख्य ऑडियो अपलोड करें", type=["mp3", "wav"], accept_multiple_files=True, key="tr3_up")
if audio_ups:
    st.session_state["audio_files"] = audio_ups

if not st.session_state["audio_files"]:
    st.markdown('<div class="empty-state">📂 कृपया मुख्य ऑडियो या गाना अपलोड करें।</div>', unsafe_allow_html=True)
else:
    for idx, f in enumerate(st.session_state["audio_files"]):
        c_t3_1, c_t3_2, c_t3_3, c_t3_4, c_t3_5 = st.columns([2.5, 1, 1, 1, 2])
        with c_t3_1:
            st.caption(f"🎵 {f.name[:20]}")
        with c_t3_2:
            st.number_input("Order", min_value=1, value=idx+1, key=f"tr3_ord_{idx}")
        with c_t3_3:
            st.number_input("Start Sec", min_value=0.0, key=f"tr3_st_{idx}")
        with c_t3_4:
            st.number_input("End Sec", min_value=0.0, value=10.0, key=f"tr3_end_{idx}")
        with c_t3_5:
            st.selectbox("म्यूज़िक मोड", ["🎵 Song (Default)", "🎻 Instrument", "🍃 Background Music"], key=f"tr3_mode_{idx}")

st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 🎼 TRACK 4: म्यूज़िक क्लिप्स टाइमलाइन — [OPTIONAL / SKIPPABLE]
# ------------------------------------------------------------------------------
st.markdown('<div class="track-card"><div class="track-title">🎼 Track 4: म्यूज़िक क्लिप्स टाइमलाइन <span class="optional-badge">OPTIONAL</span></div>', unsafe_allow_html=True)
st.markdown('<div class="guideline-box">📌 Track 2 की वीडियो क्लिप्स के लिए अलग से ऑडियो प्रबंधित करने हेतु।</div>', unsafe_allow_html=True)

if st.button("➕ नया म्यूज़िक क्लिप टाइमलाइन पर जोड़ें", key="tr4_add"):
    st.session_state["music_timeline_slots"].append({"id": len(st.session_state["music_timeline_slots"])+1})
    st.rerun()

if not st.session_state["music_timeline_slots"]:
    st.markdown('<div class="empty-state">ℹ️ अभी कोई म्यूज़िक-क्लिप टाइमलाइन स्लॉट नहीं जोड़ा गया है।</div>', unsafe_allow_html=True)
else:
    for idx, slot in enumerate(st.session_state["music_timeline_slots"]):
        c_t4_1, c_t4_2, c_t4_3, c_t4_4, c_t4_5, c_t4_6 = st.columns([2.5, 1, 1, 1, 1.5, 0.5])
        with c_t4_1:
            st.file_uploader(f"ऑडियो #{idx+1}", type=["mp3", "wav"], key=f"tr4_file_{idx}")
        with c_t4_2:
            st.number_input("Order", min_value=1, value=idx+1, key=f"tr4_ord_{idx}")
        with c_t4_3:
            st.number_input("Start", min_value=0.0, key=f"tr4_st_{idx}")
        with c_t4_4:
            st.number_input("End", min_value=1.0, value=5.0, key=f"tr4_end_{idx}")
        with c_t4_5:
            st.selectbox("मोड", ["🎵 Song", "🎻 Instrument", "🍃 Background"], key=f"tr4_mode_{idx}")
        with c_t4_6:
            if st.button("❌", key=f"tr4_del_{idx}"):
                st.session_state["music_timeline_slots"].pop(idx)
                st.rerun()

st.slider("🎛️ मास्टर म्यूज़िक वॉल्यूम (Master Music Volume)", 0.0, 1.0, 0.80, key="master_vol_tr4")
st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 📜 TRACK 6: स्क्रिप्ट, वॉयसओवर, न्यूज़ पट्टी एवं आउट्रो लेयर — [OPTIONAL]
# ------------------------------------------------------------------------------
st.markdown('<div class="track-card"><div class="track-title">📜 Track 6: स्क्रिप्ट, वॉयसओवर, न्यूज़ पट्टी एवं आउट्रो लेयर <span class="optional-badge">OPTIONAL</span></div>', unsafe_allow_html=True)

doc_file = st.file_uploader("📄 PDF या DOCX कथा ग्रन्थ अपलोड करें", type=["pdf", "docx"], key="tr6_doc")
if doc_file:
    ext = os.path.splitext(doc_file.name)[1].lower()
    text = ""
    if ext == ".pdf" and PDF_SUPPORT:
        reader = PdfReader(doc_file)
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
    elif ext == ".docx" and DOCX_SUPPORT:
        doc = docx_lib.Document(doc_file)
        text = "\n".join([p.text for p in doc.paragraphs])
    if text:
        st.session_state["story_script"] = text
        st.success("✅ दस्तावेज़ से स्क्रिप्ट पढ़ ली गई है!")

st.text_area("कथा / स्क्रिप्ट पाठ (यहाँ लिखें या एडिट करें)", height=120, key="story_script")

c_vo1, c_vo2 = st.columns(2)
with c_vo1:
    vo_choice = st.radio("वॉयसओवर चयन", ["🔘 बाबा एआई दिव्य आवाज़ (Edge-TTS)", "🔘 अपनी रिकॉर्ड की हुई आवाज़ अपलोड करें"])
with c_vo2:
    if "अपनी" in vo_choice:
        st.file_uploader("ऑडियो रिकॉर्डिंग (MP3/WAV)", type=["mp3", "wav"], key="tr6_custom_voice")
    st.checkbox("⚡ ऑटो-डकिंग (Auto-Ducking) ऑन रखें (वॉयस आते ही म्यूज़िक धीमा होगा)", value=True)

c_tk1, c_tk2 = st.columns([1, 3])
with c_tk1:
    mantra_mode = st.checkbox("🔲 मंत्र मोड ऑन करें (लूप पट्टी)")
with c_tk2:
    st.text_input("बॉटम न्यूज़ पट्टी संदेश (Ticker Strip)", value="॥ ॐ नमः शिवाय ॥ जय श्री राम", key="ticker_text")

st.text_input("आउट्रो संदेश (अंतिम संदेश)", value="वीडियो को LIKE और CHANNEL को SUBSCRIBE अवश्य करें!", key="outro_text")

# सबटाइटल स्टाइल सेटिंग्स (Track 6 के ठीक नीचे)
st.markdown("---")
st.caption("🎨 सबटाइटल स्टाइल सेटिंग्स")
c_sub1, c_sub2 = st.columns(2)
with c_sub1:
    sub_color = st.selectbox("सबटाइटल रंग", ["पीला (Gold) - Default", "सफ़ेद (White)", "हरा (Neon Green)"])
with c_sub2:
    sub_size = st.radio("फॉन्ट साइज़", ["🔘 50px", "🔘 65px (Default)", "🔘 90px"], index=1, horizontal=True)

st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# ⏱️ TRACK 5: टाइमिंग, प्रीव्यू एवं स्मार्ट इफ़ेक्ट्स कंट्रोल बोर्ड
# ------------------------------------------------------------------------------
st.markdown('<div class="track-card"><div class="track-title">⏱️ Track 5: टाइमिंग, प्रीव्यू एवं स्मार्ट इफ़ेक्ट्स कंट्रोल बोर्ड</div>', unsafe_allow_html=True)
st.markdown('<div class="guideline-box">📌 लाइव टाइम-टेबल मैपिंग एवं इफ़ेक्ट्स कंट्रोल बोर्ड (ऑटो-मैपिंग बोर्ड)।</div>', unsafe_allow_html=True)

# Auto-Time Mapping Preview Table
st.subheader("📊 ऑटो-टाइम मैपिंग (Auto-Time Mapping Table)")
if st.session_state["visual_files"]:
    st.write("| समय सीमा | दृश्य / फाइल नाम | प्रकार |")
    st.write("| :--- | :--- | :--- |")
    curr = 0.0
    for idx, f in enumerate(st.session_state["visual_files"]):
        st.write(f"| {curr:.1f}s - {curr+5.0:.1f}s | #{idx+1} {f.name[:25]} | {'🎞️ Video' if f.name.endswith(('mp4','mov')) else '🖼️ Image'} |")
        curr += 5.0
else:
    st.caption("⚠️ कोई मीडिया अपलोड नहीं है। मैपिंग टेबल खाली है।")

# Smart Effects Mode
st.subheader("🎨 इफ़ेक्ट्स कंट्रोल मोड")
fx_mode = st.radio("इफ़ेक्ट मोड चुनें", ["🔘 🤖 ऑटो-मैजिक इफ़ेक्ट्स (Default)", "🔘 🎛️ कस्टम इफ़ेक्ट्स (Manual)"], horizontal=True)

if "कस्टम" in fx_mode:
    c_fx1, c_fx2, c_fx3 = st.columns(3)
    with c_fx1:
        st.selectbox("Motion", ["Static", "Smooth Zoom In", "Smooth Zoom Out", "Pan Left/Right", "Spin & Scale"])
    with c_fx2:
        st.selectbox("Transitions", ["Fade", "Dissolve", "Glow Flash", "Radial Circle Cut", "Blur Dissolve", "Slide Wipe"])
    with c_fx3:
        st.selectbox("Overlay Effects", ["None", "Glass Shatter (शीशा टूटना + SFX)", "Light Rays"])

st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------
# 🔊 TRACK 7: SFX (साउंड इफ़ेक्ट्स) टाइमलाइन — [OPTIONAL / SKIPPABLE]
# --------------------------------------------------------------
st.markdown('<div class="track-card"><div class="track-title">🔊 Track 7: SFX (साउंड इफ़ेक्ट्स) टाइमलाइन <span class="optional-badge">OPTIONAL</span></div>', unsafe_allow_html=True)
st.markdown('<div class="guideline-box">📌 दृश्य के अनुसार शंख, डमरू, घंटी, बारिश या हवा की आवाज़ जोड़ने के लिए।</div>', unsafe_allow_html=True)

if st.button("➕ नया साउंड इफ़ेक्ट (SFX) इवेंट जोड़ें", key="tr7_add"):
    st.session_state["sfx_events"].append({"id": len(st.session_state["sfx_events"])+1})
    st.rerun()

if not st.session_state["sfx_events"]:
    st.markdown('<div class="empty-state">ℹ️ अभी कोई साउंड इफ़ेक्ट नहीं जोड़ा गया है।</div>', unsafe_allow_html=True)
else:
    sfx_preset_options = [
        "🕉️ धार्मिक: शंख नाद", "🕉️ धार्मिक: डमरू", "🕉️ धार्मिक: मंदिर की घंटी", "🕉️ धार्मिक: ओम गूंज",
        "🌧️ प्रकृति: मूसलाधार बारिश", "🌧️ प्रकृति: तेज़ हवा", "💥 सिनेमैटिक: शीशा/काँच टूटना", "💥 सिनेमैटिक: भारी धमाका", "📁 कस्टम फाइल..."
    ]
    for idx, evt in enumerate(st.session_state["sfx_events"]):
        c_sf1, c_sf2, c_sf3, c_sf4, c_sf5 = st.columns([3, 1.5, 1.5, 2, 0.5])
        with c_sf1:
            s_val = st.selectbox(f"SFX #{idx+1}", sfx_preset_options, key=f"tr7_sel_{idx}")
            if s_val == "📁 कस्टम फाइल...":
                st.file_uploader("कस्टम SFX MP3", type=["mp3","wav"], key=f"tr7_file_{idx}")
        with c_sf2:
            st.number_input("Start Sec", min_value=0.0, key=f"tr7_st_{idx}")
        with c_sf3:
            st.number_input("End Sec", min_value=0.5, value=2.0, key=f"tr7_end_{idx}")
        with c_sf4:
            st.slider("Volume", 0.0, 1.0, 0.8, key=f"tr7_vol_{idx}")
        with c_sf5:
            if st.button("❌", key=f"tr7_del_{idx}"):
                st.session_state["sfx_events"].pop(idx)
                st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# 🎆 PYTHON CLIMAX ENGINE & RENDER OPTIONS (FIXED & CONNECTED)
# ==============================================================================
import tempfile
from engine import compile_cinematic_video

st.markdown('<div class="track-card"><div class="track-title">🎆 Python Climax Engine & Render Console</div>', unsafe_allow_html=True)
st.caption("✨ ऑटो-आतिशबाज़ी स्पार्क्स (Particle Fireworks), फ़्लोटिंग बैलून्स एवं 3D 'LIKE & SUBSCRIBE' एनिमेटेड बैज विथ गोल्ड ग्लो!")

# अपलोड की गई फाइलों को डिस्क पर सेव करने का हेल्पर फंक्शन
def process_uploaded_files(file_list):
    saved_data = []
    temp_dir = tempfile.mkdtemp()
    for idx, f in enumerate(file_list):
        file_path = os.path.join(temp_dir, f.name)
        with open(file_path, "wb") as out:
            out.write(f.getbuffer())
        is_img = f.type.startswith("image") if (hasattr(f, "type") and f.type) else True
        saved_data.append({
            "path": file_path,
            "is_image": is_img,
            "start": 0.0,
            "end": 5.0,
            "ken_burns": True,
            "mode": "🎵 Song (Default)"
        })
    return saved_data

c_rnd1, c_rnd2 = st.columns(2)

with c_rnd1:
    if st.button("⚡ क्विक ड्राफ्ट रेंडर (360p Fast Test)", use_container_width=True):
        if not st.session_state["visual_files"] or not st.session_state["audio_files"]:
            st.error("❌ अनिवार्य ट्रैक्स (Track 1 और Track 3) में फाइल अपलोड करना आवश्यक है!")
        else:
            with st.spinner("⚡ 360p ड्राफ्ट वीडियो तैयार हो रहा है..."):
                try:
                    vis_data = process_uploaded_files(st.session_state["visual_files"])
                    aud_data = process_uploaded_files(st.session_state["audio_files"])
                    
                    out_path = compile_cinematic_video(
                        video_format=video_format,
                        video_quality="🔘 720p HD (तेज़ प्रोसेसिंग)",
                        visual_files=vis_data,
                        audio_files=aud_data,
                        output_path="quick_draft.mp4"
                    )
                    st.success("✅ ड्राफ्ट रेंडर तैयार है!")
                    st.video(out_path)
                except Exception as e:
                    st.error(f"❌ ड्राफ्ट रेंडरिंग एरर: {str(e)}")

with c_rnd2:
    if st.button("🎬 फाइनल वीडियो बनाएं (Full HD Render)", use_container_width=True):
        if not st.session_state["visual_files"] or not st.session_state["audio_files"]:
            st.error("❌ अनिवार्य ट्रैक्स (Track 1 और Track 3) में फाइल अपलोड करना आवश्यक है!")
        else:
            with st.spinner("🚀 मास्टर 7-ट्रैक रेंडरिंग प्रक्रिया शुरू हो गई है... कृपया प्रतीक्षा करें"):
                try:
                    # 1. फाइल्स सेव करें
                    vis_data = process_uploaded_files(st.session_state["visual_files"])
                    aud_data = process_uploaded_files(st.session_state["audio_files"])
                    
                    # 2. engine.py को पूरा डेटा भेजकर रेंडर करें
                    output_path = compile_cinematic_video(
                        video_format=video_format,
                        video_quality=video_quality,
                        visual_files=vis_data,
                        video_timeline_slots=st.session_state.get("video_timeline_slots", []),
                        audio_files=aud_data,
                        music_timeline_slots=st.session_state.get("music_timeline_slots", []),
                        master_music_vol=st.session_state.get("master_vol_tr4", 0.8),
                        sfx_events=st.session_state.get("sfx_events", []),
                        story_script=st.session_state.get("story_script", ""),
                        output_path="final_master_video.mp4"
                    )
                    
                    st.success("🎉 मास्टर वीडियो सफलतापूर्वक तैयार हो गया है!")
                    
                    # 3. वीडियो प्लेयर और डाउनलोड बटन
                    st.video(output_path)
                    with open(output_path, "rb") as file:
                        st.download_button(
                            label="📥 मास्टर वीडियो डाउनलोड करें",
                            data=file,
                            file_name="Baba_Studio_Master_Video.mp4",
                            mime="video/mp4",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"❌ रेंडरिंग एरर: {str(e)}")

st.markdown('</div>', unsafe_allow_html=True)
