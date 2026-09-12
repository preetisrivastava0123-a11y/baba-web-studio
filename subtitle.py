"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — subtitle.py
==============================================================
यह ब्लॉक "सबटाइटल इंजन" (Subtitle Engine) है।
इसका काम है:
  1) दिए गए हिंदी टेक्स्ट को एक सुंदर HTML/CSS कंटेनर में डालना
  2) Playwright के हेडलेस Chromium ब्राउज़र से उसका स्क्रीनशॉट लेना
  3) उस स्क्रीनशॉट को पारदर्शी (transparent) PNG के रूप में सेव करना

यह फाइल पूरी तरह स्वतंत्र (independent) है — इसे app.py से
अलग टेस्ट भी किया जा सकता है। पारदर्शी PNG होने की वजह से
इस सबटाइटल को आगे किसी भी वीडियो के ऊपर आसानी से ओवरले
(overlay) किया जा सकता है।
==============================================================
"""

import os

from playwright.sync_api import sync_playwright


# --------------------------------------------------------------
# सेटिंग्स (Constants) — ज़रूरत पड़ने पर आसानी से बदले जा सकते हैं
# --------------------------------------------------------------
CANVAS_WIDTH = 1600          # स्क्रीनशॉट कैनवस की चौड़ाई (px)
CANVAS_HEIGHT = 400           # स्क्रीनशॉट कैनवस की ऊँचाई (px)
FONT_SIZE_PX = 75             # टेक्स्ट का फॉन्ट साइज़


# --------------------------------------------------------------
# 1) HTML टेम्पलेट बनाने वाला फंक्शन
#    यह टेक्स्ट को एक स्टाइल्ड (styled) HTML पेज में लपेटता है
# --------------------------------------------------------------
def _build_subtitle_html(text_string: str) -> str:
    """
    दिए गए हिंदी टेक्स्ट (text_string) को एक HTML पेज में डालता है।

    ज़रूरी स्टाइल:
      - बैकग्राउंड पूरी तरह पारदर्शी (transparent) रहे
      - फॉन्ट साइज़ 75px हो
      - टेक्स्ट का रंग सफेद (white) हो
      - गहरा 3D ब्लैक शैडो (text-shadow) लगा हो ताकि अक्षर
        किसी भी बैकग्राउंड पर साफ (readable) दिखें
    """
    html_template = f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <style>
            /* पेज और बॉडी दोनों को पूरी तरह पारदर्शी रखना */
            html, body {{
                margin: 0;
                padding: 0;
                background: transparent;
                width: {CANVAS_WIDTH}px;
                height: {CANVAS_HEIGHT}px;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
            }}

            /* सबटाइटल टेक्स्ट का मुख्य कंटेनर */
            .subtitle-box {{
                font-family: 'Noto Sans Devanagari', 'Mangal', sans-serif;
                font-size: {FONT_SIZE_PX}px;
                font-weight: 700;
                color: #ffffff;               /* सफेद टेक्स्ट */
                text-align: center;
                white-space: pre-wrap;         /* मात्राएँ/लाइन-ब्रेक सही रहें */
                line-height: 1.3;
                padding: 0 40px;

                /* गहरा 3D ब्लैक शैडो — कई परतें (layers) लगाकर
                   एक "उभरा हुआ" (embossed) 3D जैसा असर बनाया गया है */
                text-shadow:
                    2px 2px 0px #000000,
                    4px 4px 0px #000000,
                    6px 6px 10px rgba(0, 0, 0, 0.8),
                    0px 0px 25px rgba(0, 0, 0, 0.9);
            }}
        </style>
    </head>
    <body>
        <div class="subtitle-box">{text_string}</div>
    </body>
    </html>
    """
    return html_template


# --------------------------------------------------------------
# 2) मुख्य फंक्शन — यही बाहर से (app.py से) बुलाया जाएगा
# --------------------------------------------------------------
def render_subtitle_html_to_png(text_string: str, output_image_path: str) -> str:
    """
    दिए गए हिंदी टेक्स्ट (text_string) का एक पारदर्शी PNG सबटाइटल
    बनाता है और उसे output_image_path पर सेव करता है।

    प्रक्रिया:
      चरण 1: टेक्स्ट से स्टाइल्ड HTML बनाना
      चरण 2: Playwright से हेडलेस Chromium शुरू करना
      चरण 3: HTML को पेज में लोड करना
      चरण 4: सिर्फ टेक्स्ट बॉक्स का पारदर्शी स्क्रीनशॉट लेना
      चरण 5: ब्राउज़र बंद करना और फाइल पथ लौटाना

    पैरामीटर:
        text_string (str)        -> जो हिंदी टेक्स्ट सबटाइटल में दिखेगा
        output_image_path (str)  -> PNG फाइल कहाँ सेव करनी है

    रिटर्न:
        output_image_path (str)  -> सफल होने पर फाइनल PNG का पथ
    """

    if not text_string or not text_string.strip():
        raise ValueError("सबटाइटल टेक्स्ट खाली है! कृपया कोई टेक्स्ट दें।")

    # --- चरण 1: स्टाइल्ड HTML तैयार करना ---
    html_content = _build_subtitle_html(text_string)

    # --- चरण 2 से 5: Playwright के साथ स्क्रीनशॉट लेना ---
    with sync_playwright() as playwright_engine:

        # हेडलेस Chromium ब्राउज़र शुरू करना
        # (headless=True मतलब कोई विंडो नहीं खुलेगी, बैकएंड पर चलेगा)
        browser = playwright_engine.chromium.launch(headless=True)

        # एक नया पेज (टैब) खोलना, जिसका बैकग्राउंड पारदर्शी हो
        page = browser.new_page(
            viewport={"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT}
        )

        # हमारा तैयार किया हुआ HTML पेज में डालना
        page.set_content(html_content)

        # फॉन्ट और लेआउट पूरी तरह लोड होने का थोड़ा इंतज़ार करना
        page.wait_for_timeout(300)

        # --- सिर्फ टेक्स्ट बॉक्स का पारदर्शी स्क्रीनशॉट लेना ---
        # omit_background=True की वजह से बैकग्राउंड सफेद/काला नहीं
        # बल्कि पूरी तरह पारदर्शी (alpha-transparent) रहेगा
        subtitle_element = page.locator(".subtitle-box")
        subtitle_element.screenshot(
            path=output_image_path,
            omit_background=True   # <-- यही पारदर्शिता (transparency) की कुंजी है
        )

        browser.close()

    return output_image_path


# --------------------------------------------------------------
# इस फाइल को सीधे चलाकर टेस्ट करने के लिए (Optional)
# --------------------------------------------------------------
if __name__ == "__main__":
    sample_text = "हर हर महादेव 🙏"
    result_path = render_subtitle_html_to_png(sample_text, "subtitle_output.png")
    print(f"✅ सबटाइटल PNG सफलतापूर्वक बनी: {result_path}")