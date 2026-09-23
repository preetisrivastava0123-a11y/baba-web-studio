"""
business_report.py
"📈 व्यापार रिपोर्ट" (Business Intelligence Report) module.

------------------------------------------------------------------------
यह क्या है
------------------------------------------------------------------------
youtube_dashboard.py पहले से जो data fetch कर चुका है (channel overview,
28-दिन का analytics trend, top videos, watch hours, shorts views) — उसी
data को दोबारा उपयोग करके यह module एक बिज़नेसमैन के टेबल जैसी रिपोर्ट
बनाता है:
    - क्या सही चल रहा है (Strengths)
    - क्या कमज़ोर है / सुधार चाहिए (Weaknesses)
    - निष्कर्ष (Overall Conclusion)
    - आगे की रणनीति (Next-step Action Plan)

------------------------------------------------------------------------
ज़रूरी बात - ईमानदारी से पढ़ें
------------------------------------------------------------------------
यह कोई "AI जादू" नहीं है। यह सिर्फ़ आपके असली Analytics नंबरों पर
साधारण, पारदर्शी नियम (rules) लगाकर निष्कर्ष निकालता है - जैसे:
"पिछले 14 दिन बनाम उससे पहले के 14 दिन में व्यूज़ 20% बढ़े/घटे"।
कोई "guaranteed viral" या "secret algorithm" वाला दावा नहीं है - ऐसा
कोई भी दावा करने वाला tool झूठ बोल रहा है, YouTube का ranking algorithm
पूरी तरह private है।

------------------------------------------------------------------------
कैसे जोड़ें (youtube_dashboard.py में सिर्फ़ 2 लाइन)
------------------------------------------------------------------------
1) फ़ाइल के ऊपर import करें:
       from business_report import render_business_report

2) render_dashboard_ui() में, "टॉप वीडियो" वाले हिस्से के ठीक बाद
   (यानी जहाँ top_videos पहले से fetch हो चुका है), यह लाइन जोड़ें:

       render_business_report(youtube, overview, rows, headers, top_videos,
                               watch_hours, shorts_views)

   ध्यान दें: यह पहले से fetch हो चुके rows/headers/top_videos/
   watch_hours/shorts_views को दोबारा इस्तेमाल करता है - इसलिए कोई नई
   API क्वोटा खर्च नहीं होगी (सिवाय upload-consistency वाले हिस्से के,
   जो एक हल्का सा extra call करता है - नीचे देखें)।
"""

import logging
from datetime import datetime, timedelta

import streamlit as st

logger = logging.getLogger("business_report")


# ---------------------------------------------------------------------------
# अपलोड कंसिस्टेंसी (पिछले 28 दिन में कितने वीडियो अपलोड हुए)
# ---------------------------------------------------------------------------
def _fetch_upload_count_28d(youtube, days=28) -> int:
    """हल्का extra API call - सिर्फ़ video ID गिनने के लिए, पूरा data नहीं।
    अगर यह fail हो जाए (quota/permission issue), तो चुपचाप None लौटाएगा -
    बाकी रिपोर्ट फिर भी बनती रहेगी।"""
    try:
        published_after = (datetime.utcnow() - timedelta(days=days)).isoformat("T") + "Z"
        resp = youtube.search().list(
            part="id", forMine=True, type="video",
            order="date", publishedAfter=published_after, maxResults=50,
        ).execute()
        return len(resp.get("items", []))
    except Exception as e:
        logger.warning(f"Upload count nahi mil paya: {e}")
        return None


# ---------------------------------------------------------------------------
# ट्रेंड एनालिसिस: पिछले 14 दिन बनाम उससे पहले के 14 दिन
# ---------------------------------------------------------------------------
def _trend(rows, col_index, label):
    """rows = analytics timeseries (day-wise)। पहले आधे बनाम दूसरे आधे
    period की तुलना करके 'बढ़त / गिरावट / स्थिर' बताता है।"""
    if not rows or len(rows) < 4:
        return {"label": label, "status": "अपर्याप्त डेटा", "change_pct": None,
                "first_half": None, "second_half": None}

    mid = len(rows) // 2
    first_half = sum(r[col_index] for r in rows[:mid])
    second_half = sum(r[col_index] for r in rows[mid:])

    if first_half == 0:
        status = "नया डेटा" if second_half > 0 else "कोई गतिविधि नहीं"
        return {"label": label, "status": status, "change_pct": None,
                "first_half": first_half, "second_half": second_half}

    change_pct = ((second_half - first_half) / first_half) * 100
    if change_pct >= 10:
        status = "बढ़त 📈"
    elif change_pct <= -10:
        status = "गिरावट 📉"
    else:
        status = "स्थिर ➡️"

    return {"label": label, "status": status, "change_pct": change_pct,
            "first_half": first_half, "second_half": second_half}


def _avg_view_duration_trend(rows, views_idx, minutes_idx):
    """औसत देखने का समय (सेकंड/व्यू) - retention का एक भरोसेमंद proxy।
    यह असली 'audience retention curve' नहीं है (वो अलग API metric है),
    लेकिन दिशा (बेहतर हो रहा है या नहीं) दिखाने के लिए काफ़ी अच्छा है।"""
    if not rows or len(rows) < 4:
        return None
    mid = len(rows) // 2

    def _avg_seconds(subset):
        total_views = sum(r[views_idx] for r in subset)
        total_minutes = sum(r[minutes_idx] for r in subset)
        if total_views == 0:
            return None
        return (total_minutes * 60) / total_views

    first_avg = _avg_seconds(rows[:mid])
    second_avg = _avg_seconds(rows[mid:])
    if first_avg is None or second_avg is None:
        return None
    change_pct = ((second_avg - first_avg) / first_avg) * 100 if first_avg else None
    return {"first_avg_sec": first_avg, "second_avg_sec": second_avg, "change_pct": change_pct}


# ---------------------------------------------------------------------------
# सबसे अच्छा / सबसे कमज़ोर वीडियो
# ---------------------------------------------------------------------------
def _best_worst_video(top_videos):
    if not top_videos:
        return None, None
    sorted_videos = sorted(top_videos, key=lambda v: v["views"], reverse=True)
    return sorted_videos[0], sorted_videos[-1]


# ---------------------------------------------------------------------------
# मुख्य रिपोर्ट रेंडरर
# ---------------------------------------------------------------------------
def render_business_report(youtube, overview, rows, headers, top_videos,
                            watch_hours, shorts_views):
    st.divider()
    st.header("📈 व्यापार रिपोर्ट — पिछले 28 दिन")
    st.caption(
        "यह रिपोर्ट आपके असली Analytics नंबरों से खुद-ब-खुद बनती है - जैसे किसी "
        "व्यापारी की बहीखाता रिपोर्ट। कोई अनुमान या 'गारंटी वाला' दावा नहीं, "
        "सिर्फ़ पिछले 14 दिन बनाम उससे पहले के 14 दिन की सीधी तुलना।"
    )

    if not rows or len(headers) < 5:
        st.info("ℹ️ रिपोर्ट बनाने के लिए पर्याप्त Analytics डेटा अभी उपलब्ध नहीं है।")
        return

    col_names = [h["name"] for h in headers]
    idx = {name: i for i, name in enumerate(col_names)}

    views_trend = _trend(rows, idx["views"], "व्यूज़")
    watch_trend = _trend(rows, idx["estimatedMinutesWatched"], "वॉच टाइम")
    likes_trend = _trend(rows, idx["likes"], "लाइक्स")
    subs_trend = _trend(rows, idx["subscribersGained"], "नए सब्सक्राइबर्स")
    duration_trend = _avg_view_duration_trend(rows, idx["views"], idx["estimatedMinutesWatched"])
    upload_count = _fetch_upload_count_28d(youtube)
    best_video, worst_video = _best_worst_video(top_videos)

    # ------------------------------------------------------------------
    # सारांश कार्ड्स
    # ------------------------------------------------------------------
    st.subheader("🔢 सारांश (पहले 14 दिन बनाम बाद के 14 दिन)")
    c1, c2, c3, c4 = st.columns(4)
    for col, t in zip([c1, c2, c3, c4], [views_trend, watch_trend, likes_trend, subs_trend]):
        with col:
            delta_str = f"{t['change_pct']:+.1f}%" if t["change_pct"] is not None else None
            st.metric(t["label"], t["status"], delta=delta_str)

    # ------------------------------------------------------------------
    # क्या सही चल रहा है (Strengths)
    # ------------------------------------------------------------------
    strengths = []
    weaknesses = []

    for t in [views_trend, watch_trend, likes_trend, subs_trend]:
        if t["change_pct"] is not None:
            if t["change_pct"] >= 10:
                strengths.append(f"**{t['label']}** में {t['change_pct']:+.1f}% की बढ़त — यह सही दिशा में जा रहा है।")
            elif t["change_pct"] <= -10:
                weaknesses.append(f"**{t['label']}** में {t['change_pct']:+.1f}% की गिरावट — इस पर ध्यान देने की ज़रूरत है।")

    if duration_trend and duration_trend["change_pct"] is not None:
        dp = duration_trend["change_pct"]
        avg_sec_now = duration_trend["second_avg_sec"]
        if dp >= 5:
            strengths.append(
                f"औसत देखने का समय बढ़कर लगभग **{avg_sec_now:.0f} सेकंड/व्यू** हो गया है "
                f"({dp:+.1f}%) — मतलब लोग आपका कंटेंट पहले से ज़्यादा देर देख रहे हैं, "
                "जो algorithm के लिए एक अच्छा संकेत है।"
            )
        elif dp <= -5:
            weaknesses.append(
                f"औसत देखने का समय घटकर लगभग **{avg_sec_now:.0f} सेकंड/व्यू** रह गया है "
                f"({dp:+.1f}%) — यानी शुरुआती hook या content की लंबाई पर दोबारा ध्यान देना होगा।"
            )

    if upload_count is not None:
        if upload_count >= 8:
            strengths.append(f"पिछले 28 दिन में **{upload_count} वीडियो** अपलोड हुए — consistency अच्छी है।")
        elif upload_count >= 1:
            weaknesses.append(
                f"पिछले 28 दिन में सिर्फ़ **{upload_count} वीडियो** अपलोड हुए — ज़्यादातर भक्ति चैनलों में "
                "हफ़्ते में 2-3 वीडियो consistency ग्रोथ को काफ़ी तेज़ करती है।"
            )
        else:
            weaknesses.append("पिछले 28 दिन में कोई नया वीडियो अपलोड नहीं हुआ — consistency सबसे बड़ा growth factor है।")

    if best_video and worst_video and best_video["video_id"] != worst_video["video_id"]:
        strengths.append(
            f"सबसे अच्छा वीडियो **\"{best_video['title']}\"** रहा — {best_video['views']:,} व्यूज़। "
            "इसके टाइटल/टॉपिक का पैटर्न आगे भी दोहराया जा सकता है।"
        )
        if worst_video["views"] > 0:
            weaknesses.append(
                f"सबसे कमज़ोर वीडियो **\"{worst_video['title']}\"** रहा — सिर्फ़ {worst_video['views']:,} व्यूज़। "
                "टाइटल/थंबनेल/टॉपिक की तुलना best video से करके फ़र्क़ समझें।"
            )

    sc1, sc2 = st.columns(2)
    with sc1:
        st.subheader("✅ क्या सही चल रहा है")
        if strengths:
            for s in strengths:
                st.markdown(f"- {s}")
        else:
            st.caption("अभी कोई स्पष्ट मज़बूत संकेत नहीं दिखा।")
    with sc2:
        st.subheader("⚠️ कहाँ सुधार चाहिए")
        if weaknesses:
            for w in weaknesses:
                st.markdown(f"- {w}")
        else:
            st.caption("अभी कोई बड़ी कमज़ोरी नहीं दिखी।")

    # ------------------------------------------------------------------
    # निष्कर्ष
    # ------------------------------------------------------------------
    st.subheader("🧾 निष्कर्ष")
    score = len(strengths) - len(weaknesses)
    if score >= 2:
        verdict = "आपका चैनल इस समय **बढ़त की दिशा में** है।"
    elif score <= -2:
        verdict = "आपके चैनल को इस समय **ध्यान और बदलाव** की ज़रूरत है।"
    else:
        verdict = "आपका चैनल फ़िलहाल **स्थिर स्थिति** में है — न बड़ी बढ़त, न बड़ी गिरावट।"
    st.markdown(verdict)

    # ------------------------------------------------------------------
    # आगे की रणनीति
    # ------------------------------------------------------------------
    st.subheader("🎯 आगे की रणनीति")
    strategy_points = []
    if upload_count is not None and upload_count < 8:
        strategy_points.append("अपलोड की संख्या बढ़ाएं — हफ़्ते में कम से कम 2 वीडियो का लक्ष्य रखें।")
    if duration_trend and duration_trend["change_pct"] is not None and duration_trend["change_pct"] <= -5:
        strategy_points.append("पहले 15 सेकंड का hook मज़बूत करें ताकि देखने का समय ना घटे।")
    if views_trend["change_pct"] is not None and views_trend["change_pct"] <= -10:
        strategy_points.append("थंबनेल और टाइटल में बदलाव करके टेस्ट करें - जो टॉपिक पहले चला था, वैसा एक और वीडियो बनाएं।")
    if best_video:
        strategy_points.append(
            f"\"{best_video['title']}\" जैसे टॉपिक/फॉर्मेट पर 1-2 और वीडियो बनाने पर विचार करें।"
        )
    if not strategy_points:
        strategy_points.append("मौजूदा रफ़्तार और कंटेंट स्टाइल को जारी रखें - सब कुछ स्थिर दिशा में चल रहा है।")

    for i, sp in enumerate(strategy_points, 1):
        st.markdown(f"{i}. {sp}")

    st.caption(
        "⚠️ ध्यान दें: यह रिपोर्ट सिर्फ़ आपके अपने पिछले डेटा की तुलना पर आधारित है, "
        "किसी बाहरी 'secret' जानकारी पर नहीं। YouTube का algorithm निजी है, इसलिए कोई भी "
        "tool 100% गारंटी नहीं दे सकता - यह सिर्फ़ दिशा दिखाने के लिए है।"
    )
