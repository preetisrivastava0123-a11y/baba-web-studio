"""
topic_trend_analysis.py
"🧭 टॉपिक + ट्रेंड इंटेलिजेंस" module - दो हिस्से:

1) render_own_topic_performance(youtube, yta)
   आपके अपने चैनल के वीडियो को टॉपिक (भजन/आरती/चालीसा/कथा/कीर्तन/मंत्र...)
   और फॉर्मेट (Shorts बनाम Long-form) के हिसाब से बाँटकर दिखाता है कि
   कौन सा टॉपिक/फॉर्मेट ज़्यादा views, watch-time और likes ला रहा है।

2) render_niche_intelligence(youtube)
   पूरे धार्मिक (dharmik) niche में अभी क्या ज़्यादा चल रहा है - title के
   common शब्द/pattern, tags, और Shorts बनाम Long-form का response फ़र्क़।
   यह youtube_dashboard.py के मौजूदा "Niche Trend Explorer" का ही
   बेहतर/विस्तृत version है (उसकी जगह इस्तेमाल किया जा सकता है)।

------------------------------------------------------------------------
ज़रूरी सीमाएँ - ईमानदारी से पढ़ें
------------------------------------------------------------------------
- YouTube का कोई public "trending" API नहीं है। यह सिर्फ़ हाल में
  पब्लिश हुए, ज़्यादा-views वाले वीडियो खोजकर pattern निकालता है -
  यह "inspiration" है, guarantee नहीं।
- Shorts बनाम Long-form का बँटवारा वीडियो की लंबाई (duration) से किया
  जाता है (≤180 सेकंड = Shorts माना गया) - यह YouTube का आधिकारिक
  "is this a Short" flag नहीं है, बस एक भरोसेमंद अनुमान है।
- टॉपिक पहचान टाइटल में मौजूद keywords (भजन/आरती/कथा वगैरह) से होती
  है। अगर टाइटल में टॉपिक शब्द नहीं है, तो वह "अन्य" में गिना जाएगा।
- दूसरे चैनलों के वीडियो का "likes" कभी-कभी owner द्वारा छुपाया गया
  हो सकता है - ऐसे में वह गिनती में शामिल नहीं होगा (None रहेगा)।

------------------------------------------------------------------------
कैसे जोड़ें (youtube_dashboard.py में)
------------------------------------------------------------------------
ऊपर import करें:
    from topic_trend_analysis import render_own_topic_performance, render_niche_intelligence

फिर render_dashboard_ui() में, टॉप वीडियो सेक्शन के बाद:
    render_own_topic_performance(youtube, yta)

और मौजूदा "_render_niche_trend_explorer(youtube)" वाली लाइन की जगह
(या उसके अतिरिक्त, अगर दोनों रखने हैं):
    render_niche_intelligence(youtube)
"""

import re
import logging
from datetime import datetime, timedelta
from collections import Counter

import streamlit as st

logger = logging.getLogger("topic_trend_analysis")

SHORTS_MAX_SECONDS = 180  # ≤3 मिनट = Shorts माना गया (अनुमान, आधिकारिक flag नहीं)

TOPIC_KEYWORDS = {
    "भजन": ["bhajan", "भजन"],
    "आरती": ["aarti", "आरती"],
    "चालीसा": ["chalisa", "चालीसा"],
    "कथा": ["katha", "कथा"],
    "कीर्तन": ["kirtan", "कीर्तन"],
    "मंत्र": ["mantra", "मंत्र"],
    "पाठ": ["path", "पाठ"],
    "प्रवचन": ["pravachan", "प्रवचन"],
    "स्तुति/स्तोत्र": ["stuti", "stotra", "स्तुति", "स्तोत्र"],
    "हनुमान": ["hanuman", "हनुमान", "बजरंगबली", "bajrangbali"],
    "शिव": ["shiv", "शिव", "महादेव", "mahadev", "रुद्र", "rudra"],
    "कृष्ण": ["krishna", "कृष्ण", "श्याम", "shyam", "कान्हा", "kanha"],
    "राम": ["ram katha", "rama", "राम", "रामायण", "ramayan"],
    "देवी माँ": ["devi", "देवी", "माता", "mata", "दुर्गा", "durga", "लक्ष्मी", "laxmi", "lakshmi"],
    "गीता/सत्संग": ["gita", "गीता", "satsang", "सत्संग"],
    "व्रत/त्यौहार": ["vrat", "व्रत", "ekadashi", "एकादशी", "पूजा विधि", "puja vidhi"],
    "सुंदरकांड": ["sundarkand", "सुंदरकांड", "sunderkand"],
}

STOPWORDS = set([
    "the", "of", "and", "to", "for", "in", "on", "a", "is", "with", "video", "official",
    "live", "new", "2025", "2026", "hd", "full", "song", "you", "your",
    "के", "का", "की", "है", "में", "से", "को", "और", "ये", "यह", "पर", "हैं",
    "एक", "भी", "तो", "ही", "जी", "श्री", "वीडियो",
])


def _parse_iso_duration_seconds(duration: str):
    if not duration:
        return None
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return None
    h, m, s = (int(x) if x else 0 for x in match.groups())
    return h * 3600 + m * 60 + s


def _classify_format(duration_sec):
    if duration_sec is None:
        return "अज्ञात"
    return "Shorts" if duration_sec <= SHORTS_MAX_SECONDS else "Long-form"


def _extract_topic(title: str) -> str:
    title_lower = (title or "").lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in title_lower:
                return topic
    return "अन्य"


def _word_frequency(titles, top_n=15):
    counter = Counter()
    for title in titles:
        words = re.findall(r"[\w\u0900-\u097F]+", title.lower())
        for w in words:
            if len(w) <= 2 or w in STOPWORDS:
                continue
            counter[w] += 1
    return counter.most_common(top_n)


def _fetch_own_video_topic_data(youtube, yta, days=90, max_videos=50):
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    resp = yta.reports().query(
        ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
        metrics="views,estimatedMinutesWatched,likes",
        dimensions="video", sort="-views", maxResults=max_videos,
    ).execute()
    rows = resp.get("rows", [])
    if not rows:
        return []

    video_ids = [r[0] for r in rows]
    analytics_map = {r[0]: {"views": r[1], "watch_minutes": r[2], "likes": r[3]} for r in rows}

    details = {}
    try:
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            vresp = youtube.videos().list(part="snippet,contentDetails", id=",".join(batch)).execute()
            for v in vresp.get("items", []):
                details[v["id"]] = v
    except Exception as e:
        logger.warning(f"Video details nahi mil paye: {e}")

    results = []
    for vid in video_ids:
        d = details.get(vid)
        a = analytics_map[vid]
        title = d["snippet"]["title"] if d else vid
        duration_sec = _parse_iso_duration_seconds(d["contentDetails"]["duration"]) if d else None
        results.append({
            "video_id": vid, "title": title,
            "views": a["views"], "watch_minutes": a["watch_minutes"], "likes": a["likes"],
            "format": _classify_format(duration_sec), "topic": _extract_topic(title),
            "duration_sec": duration_sec,
        })
    return results


def _aggregate(video_data, key):
    agg = {}
    for v in video_data:
        k = v[key]
        d = agg.setdefault(k, {"views": 0, "watch_minutes": 0, "likes": 0, "count": 0})
        d["views"] += v["views"]
        d["watch_minutes"] += v["watch_minutes"]
        d["likes"] += v["likes"]
        d["count"] += 1
    for d in agg.values():
        d["avg_views_per_video"] = d["views"] / d["count"] if d["count"] else 0
        d["avg_watch_sec_per_view"] = (d["watch_minutes"] * 60 / d["views"]) if d["views"] else 0
    return agg


def render_own_topic_performance(youtube, yta):
    st.divider()
    st.header("🧭 आपके वीडियो — टॉपिक और फॉर्मेट के हिसाब से परफॉर्मेंस")
    st.caption("पिछले 90 दिनों के वीडियो, टॉपिक (टाइटल से) और फॉर्मेट (Shorts/Long) के हिसाब से बाँटे गए।")

    if st.button("🔄 टॉपिक एनालिसिस लोड/रीफ्रेश करें", key="topic_perf_refresh_btn"):
        with st.spinner("डेटा जोड़ा जा रहा है..."):
            try:
                st.session_state["topic_perf_data"] = _fetch_own_video_topic_data(youtube, yta)
            except Exception as e:
                st.error(f"डेटा लाने में दिक्कत: {e}")

    video_data = st.session_state.get("topic_perf_data")
    if not video_data:
        st.info("ℹ️ ऊपर बटन दबाकर एनालिसिस शुरू करें।")
        return

    topic_agg = _aggregate(video_data, "topic")
    st.subheader("📚 टॉपिक-वार परफॉर्मेंस")
    topic_table = sorted(
        [{"टॉपिक": k, "वीडियो संख्या": v["count"], "कुल व्यूज़": v["views"],
          "औसत व्यूज़/वीडियो": round(v["avg_views_per_video"]),
          "औसत देखने का समय (सेकंड)": round(v["avg_watch_sec_per_view"]),
          "कुल लाइक्स": v["likes"]} for k, v in topic_agg.items()],
        key=lambda r: r["औसत व्यूज़/वीडियो"], reverse=True,
    )
    st.dataframe(topic_table, use_container_width=True, hide_index=True)
    st.bar_chart({row["टॉपिक"]: row["औसत व्यूज़/वीडियो"] for row in topic_table})

    format_agg = _aggregate(video_data, "format")
    st.subheader("🎬 Shorts बनाम Long-form")
    format_table = sorted(
        [{"फॉर्मेट": k, "वीडियो संख्या": v["count"], "कुल व्यूज़": v["views"],
          "औसत व्यूज़/वीडियो": round(v["avg_views_per_video"]),
          "औसत देखने का समय (सेकंड)": round(v["avg_watch_sec_per_view"])}
         for k, v in format_agg.items() if k != "अज्ञात"],
        key=lambda r: r["औसत व्यूज़/वीडियो"], reverse=True,
    )
    st.dataframe(format_table, use_container_width=True, hide_index=True)

    st.subheader("🧾 निष्कर्ष")
    if topic_table:
        best_topic = topic_table[0]
        st.markdown(
            f"- सबसे अच्छा टॉपिक: **{best_topic['टॉपिक']}** "
            f"(औसत {best_topic['औसत व्यूज़/वीडियो']:,} व्यूज़/वीडियो) — इस पर ज़्यादा वीडियो बनाना फ़ायदेमंद रहेगा।"
        )
    if len(format_table) >= 2:
        best_format = format_table[0]
        st.markdown(
            f"- सबसे अच्छा फॉर्मेट: **{best_format['फॉर्मेट']}** "
            f"(औसत {best_format['औसत व्यूज़/वीडियो']:,} व्यूज़/वीडियो)।"
        )
    elif len(format_table) == 1:
        st.markdown(
            f"- अभी तक सिर्फ़ **{format_table[0]['फॉर्मेट']}** फॉर्मेट में वीडियो बने हैं — "
            "दूसरा फॉर्मेट भी test करके तुलना करना फ़ायदेमंद रहेगा।"
        )


def _fetch_niche_intelligence(youtube, query, days=14, limit=25):
    published_after = (datetime.utcnow() - timedelta(days=days)).isoformat("T") + "Z"
    resp = youtube.search().list(
        part="snippet", q=query, type="video", order="viewCount",
        publishedAfter=published_after, maxResults=limit,
    ).execute()
    items = resp.get("items", [])
    video_ids = [i["id"]["videoId"] for i in items]
    if not video_ids:
        return []

    detail_map = {}
    try:
        vresp = youtube.videos().list(part="statistics,contentDetails,snippet", id=",".join(video_ids)).execute()
        for v in vresp.get("items", []):
            detail_map[v["id"]] = v
    except Exception as e:
        logger.warning(f"Niche video details nahi mile: {e}")

    results = []
    for i in items:
        vid = i["id"]["videoId"]
        v = detail_map.get(vid)
        if not v:
            continue
        views = int(v["statistics"].get("viewCount", 0))
        likes = int(v["statistics"]["likeCount"]) if "likeCount" in v["statistics"] else None
        duration_sec = _parse_iso_duration_seconds(v["contentDetails"].get("duration"))
        results.append({
            "title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
            "views": views, "likes": likes, "format": _classify_format(duration_sec),
            "tags": v["snippet"].get("tags", []),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    results.sort(key=lambda r: r["views"], reverse=True)
    return results


def render_niche_intelligence(youtube):
    st.divider()
    st.header("🔎 धार्मिक Niche इंटेलिजेंस — बाहर क्या ज़्यादा चल रहा है")
    st.caption(
        "⚠️ यह असली 'trending' API नहीं है (YouTube पब्लिक नहीं करता) — हाल में पब्लिश हुए "
        "ज़्यादा-views वाले वीडियो के title/tags/format से pattern निकाला जाता है। सिर्फ़ "
        "inspiration के लिए, गारंटी नहीं।"
    )
    query = st.text_input(
        "Keywords (ज़रूरत हो तो बदल सकते हैं)",
        value=(
            "bhajan OR katha OR pravachan OR aarti OR chalisa OR kirtan OR "
            "hanuman OR shiv OR krishna OR ram katha OR devi mata OR gita OR "
            "satsang OR vrat katha OR sundarkand OR mantra"
        ),
        key="niche_intel_query",
    )
    days = st.slider("कितने दिन पुराने वीडियो देखें", 1, 30, 14, key="niche_intel_days")

    if st.button("🔍 एनालिसिस करें", key="niche_intel_search_btn"):
        with st.spinner("खोजा जा रहा है..."):
            try:
                st.session_state["niche_intel_results"] = _fetch_niche_intelligence(youtube, query, days=days)
            except Exception as e:
                st.error(f"खोज में दिक्कत आई: {e}")

    results = st.session_state.get("niche_intel_results")
    if not results:
        return

    st.subheader("🎬 Shorts बनाम Long-form (इस niche में)")
    fmt_counter = {}
    for r in results:
        d = fmt_counter.setdefault(r["format"], {"views": 0, "count": 0})
        d["views"] += r["views"]
        d["count"] += 1
    fmt_table = [
        {"फॉर्मेट": k, "वीडियो संख्या": v["count"], "औसत व्यूज़": round(v["views"] / v["count"])}
        for k, v in fmt_counter.items() if k != "अज्ञात" and v["count"] > 0
    ]
    if fmt_table:
        st.dataframe(fmt_table, use_container_width=True, hide_index=True)

    st.subheader("📝 टाइटल में सबसे ज़्यादा दिखने वाले शब्द")
    word_freq = _word_frequency([r["title"] for r in results])
    if word_freq:
        st.markdown(", ".join([f"**{w}** ({c})" for w, c in word_freq]))
    else:
        st.caption("कोई साझा शब्द नहीं मिला।")

    st.subheader("🏷️ सबसे ज़्यादा इस्तेमाल हुए Tags")
    tag_counter = Counter()
    for r in results:
        for t in r["tags"]:
            tag_counter[t] += 1
    top_tags = tag_counter.most_common(15)
    if top_tags:
        st.markdown(", ".join([f"**{t}** ({c})" for t, c in top_tags]))
    else:
        st.caption("इन वीडियो में public tags नहीं मिले।")

    st.subheader("🏆 इस niche के टॉप वीडियो")
    for r in results[:10]:
        likes_str = f"{r['likes']:,} likes" if r["likes"] is not None else "likes छुपे हैं"
        st.markdown(f"**[{r['title']}]({r['url']})** — {r['channel']} · {r['views']:,} views · {likes_str} · {r['format']}")

    st.subheader("🧾 निष्कर्ष एवं सुझाव")
    if fmt_table:
        best_fmt = max(fmt_table, key=lambda r: r["औसत व्यूज़"])
        st.markdown(f"- इस niche में **{best_fmt['फॉर्मेट']}** फॉर्मेट को औसतन ज़्यादा response मिल रहा है।")
    if word_freq:
        top_words = ", ".join([w for w, _ in word_freq[:5]])
        st.markdown(f"- टाइटल में **{top_words}** जैसे शब्द बार-बार दिख रहे हैं — अपने अगले टाइटल में इनका उपयोग सोचें।")
    if top_tags:
        top_tag_words = ", ".join([t for t, _ in top_tags[:5]])
        st.markdown(f"- सबसे ज़्यादा इस्तेमाल हुए tags: **{top_tag_words}** — इन्हें अपने वीडियो में जोड़ने पर विचार करें।")
