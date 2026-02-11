#!/usr/bin/env python3
"""
道徳経 note.com 自動投稿スクリプト
JST 20:00 に1章ずつ投稿（cron経由）

使い方:
  python3 note_auto_post.py          # 次の未投稿章を投稿
  python3 note_auto_post.py --dry    # ドライラン（投稿しない）
  python3 note_auto_post.py --ch 3   # 指定章番号を投稿
"""
import json, re, uuid, os, io, sys, time
from pathlib import Path
from curl_cffi import requests, CurlMime
from PIL import Image
from google import genai
from google.genai import types

# === Config ===
BASE_DIR = Path("/home/ec2-user/www/work/dao_de_jing")
PROTO_DIR = BASE_DIR / "prototype"
IMG_DIR = BASE_DIR / "img"
SCRIPTS_DIR = BASE_DIR / "scripts"
STATE_FILE = SCRIPTS_DIR / "post_state.json"

LOGIN_FILE = Path("/home/ec2-user/.config/note/flow_login")
GEMINI_KEY_FILE = Path("/home/ec2-user/.config/google/gemini_api_key")
MAGAZINE_KEY = "m5335c95b0a8d"

CHARSHEET_PATH = IMG_DIR / "charsheet.jpg"
STYLE_REF_PATH = Path("/home/ec2-user/www/work/collab-laozi-sezon.jpg")

# === Chapter definitions ===
CHAPTERS = [
    {"file": "ch00-purple-clouds.md", "pattern": None, "title": "序章　紫気東来", "single": True},
    {"file": "ch01-dao.md", "header": "第一話　名前のない何か", "title": "第一話　名前のない何か"},
    {"file": "ch01-dao.md", "header": "第二話　水は低きに流れる", "title": "第二話　水は低きに流れる"},
    {"file": "ch01-dao.md", "header": "第三話　器の中身", "title": "第三話　器の中身"},
    {"file": "ch01-dao.md", "header": "第四話　じっちゃん、矛盾してません？", "title": "第四話　じっちゃん、矛盾してません？"},
    {"file": "ch01-dao.md", "header": "第五話　朴のままで", "title": "第五話　朴のままで"},
    {"file": "ch02-de.md", "header": "第六話　商人がやってきた", "title": "第六話　商人がやってきた"},
    {"file": "ch02-de.md", "header": "第七話　将軍の涙", "title": "第七話　将軍の涙"},
    {"file": "ch02-de.md", "header": "第八話　母と子", "title": "第八話　母と子"},
    {"file": "ch02-de.md", "header": "第九話　学者の敗北", "title": "第九話　学者の敗北"},
    {"file": "ch02-de.md", "header": "第十話　モーちゃんの教え", "title": "第十話　モーちゃんの教え"},
    {"file": "ch03-wuwei.md", "header": "第十一話　じっちゃん、何もしてないですよね", "title": "第十一話　じっちゃん、何もしてないですよね"},
    {"file": "ch03-wuwei.md", "header": "第十二話　統治の逆説", "title": "第十二話　統治の逆説"},
    {"file": "ch03-wuwei.md", "header": "第十三話　夜の会話", "title": "第十三話　夜の会話"},
    {"file": "ch03-wuwei.md", "header": "第十四話　尹喜、料理を作る", "title": "第十四話　尹喜、料理を作る"},
    {"file": "ch03-wuwei.md", "header": "第十五話　柔と剛", "title": "第十五話　柔と剛"},
    {"file": "ch04-xuan.md", "header": "第十六話　孔子が来た", "title": "第十六話　孔子が来た"},
    {"file": "ch04-xuan.md", "header": "第十七話　谷を見下ろして", "title": "第十七話　谷を見下ろして"},
    {"file": "ch04-xuan.md", "header": "第十八話　セゾンの噂", "title": "第十八話　セゾンの噂"},
    {"file": "ch04-xuan.md", "header": "第十九話　赤子に還る", "title": "第十九話　赤子に還る"},
    {"file": "ch04-xuan.md", "header": "第二十話　竹簡は増えている", "title": "第二十話　竹簡は増えている"},
    {"file": "ch05-exit.md", "header": "第二十一話　予感", "title": "第二十一話　予感"},
    {"file": "ch05-exit.md", "header": "第二十二話　最後の夜", "title": "第二十二話　最後の夜"},
    {"file": "ch05-exit.md", "header": "第二十三話　出関", "title": "第二十三話　出関"},
    {"file": "ch06-epilogue.md", "pattern": None, "title": "終章　道は続く", "single": True},
]

# Eyecatch prompts per chapter
EYECATCH_PROMPTS = {
    2: "Inside an ancient Chinese archive room. A young guard (Yinxi) pours water from a jug while watching it flow, while an elderly sage (Laozi) watches approvingly. Bamboo scrolls around. Morning light.",
    3: "An elderly sage (Laozi) holds an empty clay bowl, showing it to a puzzled young guard (Yinxi) in Chinese armor. Archive room with bamboo scrolls. Warm lighting.",
    4: "A young guard (Yinxi) arguing with an elderly sage (Laozi) at a desk. Yinxi looks frustrated, gesturing. Laozi smiles mysteriously. Chinese archive room.",
    5: "An elderly sage (Laozi) carving a small piece of unfinished wood (朴), while a young guard (Yinxi) watches curiously. Peaceful courtyard of a Chinese fortress.",
    6: "A traveling merchant with goods arriving at a grand Chinese fortress gate. An elderly sage sits nearby looking uninterested. Warm golden light.",
    7: "A weeping general in armor kneeling at a fortress gate. An elderly sage (Laozi) watches calmly from a bench nearby. Dramatic sky.",
    8: "A mother holding a baby, standing at a fortress gate. An elderly sage (Laozi) looking at the baby with rare tenderness. Soft warm light.",
    9: "A proud scholar with many scrolls confronting an elderly sage (Laozi) who looks annoyed. Chinese fortress courtyard. Tense atmosphere.",
    10: "A large blue-black water buffalo (Mo-chan) standing serenely in a meadow. A young guard watches in wonder. Sunset light.",
    11: "An elderly sage (Laozi) lying on a bench doing absolutely nothing. A young guard (Yinxi) standing with a broom, looking exasperated. Chinese fortress courtyard.",
    12: "Two figures sitting at a table discussing governance. Elderly sage (Laozi) gesturing calmly, young guard (Yinxi) taking notes. Night scene with lantern light.",
    13: "Night scene. An elderly sage (Laozi) writing on bamboo scrolls by candlelight. A young guard (Yinxi) peeks through a doorway. Quiet, intimate moment.",
    14: "A young guard (Yinxi) cooking in a kitchen, steam rising from pots. An elderly sage (Laozi) sitting nearby sniffing the air appreciatively. Warm domestic scene.",
    15: "Water dripping on a stone, creating a small hole. An elderly sage (Laozi) and young guard (Yinxi) watching together. Metaphorical scene about softness conquering hardness.",
    16: "A distinguished middle-aged man (Confucius) arriving at a fortress gate with followers. An elderly sage (Laozi) napping in the background. Comic contrast.",
    17: "Two figures standing at the edge of a cliff looking down into a misty valley. Elderly sage (Laozi) and young guard (Yinxi). Philosophical atmosphere.",
    18: "A young guard (Yinxi) telling stories about a distant Indian sage to an elderly sage (Laozi). Map or distant landscape visible. Evening scene.",
    19: "An elderly sage (Laozi) looking tenderly at a baby in a mother's arms. Rare emotional moment. Soft golden light.",
    20: "Night scene. A desk with growing pile of bamboo scrolls. Moonlight through window. A young guard (Yinxi) checking the pile. Quiet anticipation.",
    21: "Dawn scene. An elderly sage (Laozi) packing a small bag near a water buffalo. A young guard (Yinxi) watching with a sense of foreboding. Fortress gate in background.",
    22: "Night scene. Two figures sitting on a rooftop under stars. Elderly sage (Laozi) and young guard (Yinxi). Last night together. Bittersweet atmosphere.",
    23: "Dawn scene. An elderly sage (Laozi) riding a water buffalo through a fortress gate toward the rising sun. A young guard (Yinxi) watching from behind. Epic farewell.",
    24: "Night scene. A young guard (Yinxi) sitting alone on a rooftop with bamboo scrolls, looking up at a starry sky. Peaceful but lonely. The fortress gate below.",
}

DEFAULT_PROMPT = "A wide landscape scene from an ancient Chinese fortress (Hangu Pass). An elderly sage with white beard (Laozi) and a young armored guard (Yinxi) in a philosophical moment. Warm golden tones."


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"next_chapter": 2, "posted": []}  # 0=序章(済), 1=1章(済)


def save_state(state):
    SCRIPTS_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def extract_chapter(ch_info):
    """ファイルから指定章のテキストを抽出"""
    filepath = PROTO_DIR / ch_info["file"]
    content = filepath.read_text()

    if ch_info.get("single"):
        # 序章・終章: ファイル全体（# タイトル行と最初の---を除く）
        lines = content.split('\n')
        # Skip title line and first ---
        start = 0
        for i, line in enumerate(lines):
            if line.strip() == '---':
                start = i + 1
                break
        body = '\n'.join(lines[start:]).strip()
        return body

    header = ch_info["header"]
    # Find this chapter's content between ## headers
    # Content starts after the header line and optional --- separator
    pattern = rf'^## {re.escape(header)}\s*\n+(?:---\n+)?(.*?)(?=\n---\n+## |\n## |\Z)'
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
    if match:
        return match.group(1).strip()
    
    raise ValueError(f"Chapter not found: {header} in {ch_info['file']}")


def text_to_html(text):
    """Markdown text to note.com HTML"""
    paragraphs = text.split('\n')
    html_parts = []
    for p in paragraphs:
        p = p.strip()
        if p == '---':
            html_parts.append(f'<p name="{uuid.uuid4()}" id="{uuid.uuid4()}">＊　＊　＊</p>')
        elif p:
            p = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', p)
            # Handle furigana: 《text》 → just keep as is for note
            uid = str(uuid.uuid4())
            html_parts.append(f'<p name="{uid}" id="{uid}">{p}</p>')
    return ''.join(html_parts)


def generate_eyecatch(ch_idx):
    """Gemini でアイキャッチ画像生成"""
    gemini_key = GEMINI_KEY_FILE.read_text().strip()
    client = genai.Client(api_key=gemini_key)
    
    prompt_detail = EYECATCH_PROMPTS.get(ch_idx, DEFAULT_PROMPT)
    prompt = f"""Create a wide landscape illustration (16:9, 1280x670) for a light novel chapter.

{prompt_detail}

Style: Match the warm sepia/golden toned manga style of image 1. Clean anime linework, warm palette. Characters should match image 2 designs.
"""
    
    parts = [
        types.Part.from_bytes(data=STYLE_REF_PATH.read_bytes(), mime_type="image/jpeg"),
        types.Part.from_bytes(data=CHARSHEET_PATH.read_bytes(), mime_type="image/jpeg"),
        types.Part.from_text(text=prompt),
    ]
    
    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[types.Content(parts=parts)],
        config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
    )
    
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            img = Image.open(io.BytesIO(part.inline_data.data))
            if img.width < img.height:
                w, h = img.size
                new_h = int(w * 670 / 1280)
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))
            img = img.resize((1280, 670), Image.LANCZOS)
            
            # Save locally
            out_path = IMG_DIR / f"eyecatch-ch{ch_idx:02d}.jpg"
            img.save(str(out_path), "JPEG", quality=92)
            
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=92)
            return buf.getvalue(), str(out_path)
    
    return None, None


def post_to_note(title, html_body, body_length, eyecatch_data, ch_idx):
    """note.com にログイン→投稿"""
    creds = LOGIN_FILE.read_text().strip().split('\n')
    email, password = creds[0], creds[1]
    
    session = requests.Session(impersonate="chrome")
    
    # Login
    resp = session.post(
        "https://note.com/api/v1/sessions/sign_in",
        json={"login": email, "password": password},
        headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://note.com",
            "Referer": "https://note.com/login",
        }
    )
    assert resp.status_code == 201, f"Login failed: {resp.status_code}"
    print(f"  Login OK")
    
    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://editor.note.com",
        "Referer": "https://editor.note.com/",
    }
    
    # Create draft
    resp = session.post(
        "https://note.com/api/v1/text_notes",
        json={"template_key": None},
        headers=headers,
    )
    assert resp.status_code == 201, f"Draft create failed: {resp.status_code}"
    draft = resp.json()["data"]
    note_id = draft["id"]
    note_key = draft["key"]
    print(f"  Draft: id={note_id}, key={note_key}")
    
    # Save draft
    resp = session.post(
        f"https://note.com/api/v1/text_notes/draft_save?id={note_id}&is_temp_saved=false",
        json={
            "body": html_body,
            "body_length": body_length,
            "name": title,
            "index": False,
            "is_lead_form": False,
        },
        headers=headers,
    )
    assert resp.status_code == 201, f"Draft save failed: {resp.status_code}"
    print(f"  Draft saved")
    
    # Upload eyecatch
    if eyecatch_data:
        mp = CurlMime()
        mp.addpart(name="note_id", data=str(note_id))
        mp.addpart(name="width", data="1280")
        mp.addpart(name="height", data="670")
        eyecatch_path = str(IMG_DIR / f"eyecatch-ch{ch_idx:02d}.jpg")
        mp.addpart(name="file", filename="eyecatch.jpg", content_type="image/jpeg",
                   local_path=eyecatch_path)
        
        resp = session.post(
            "https://note.com/api/v1/image_upload/note_eyecatch",
            multipart=mp,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://editor.note.com",
                "Referer": "https://editor.note.com/",
            },
        )
        if resp.status_code == 201:
            print(f"  Eyecatch uploaded: {resp.json()['data']['url']}")
        else:
            print(f"  Eyecatch upload failed: {resp.status_code}")
    
    # Publish
    note_title = f"{title} ── 道徳経"
    resp = session.put(
        f"https://note.com/api/v1/text_notes/{note_id}",
        json={
            "author_ids": [],
            "body_length": body_length,
            "disable_comment": False,
            "exclude_from_creator_top": False,
            "exclude_ai_learning_reward": False,
            "free_body": html_body,
            "hashtags": ["道徳経", "老子", "ラノベ", "東洋思想", "尹喜"],
            "image_keys": [],
            "index": False,
            "is_refund": False,
            "limited": False,
            "magazine_keys": [MAGAZINE_KEY],
            "name": note_title,
            "pay_body": "",
            "price": 0,
            "send_notifications_flag": True,
            "separator": None,
            "slug": f"slug-{note_key}",
            "status": "published",
            "circle_permissions": [],
            "discount_campaigns": [],
            "lead_form": {"is_active": False, "consent_url": ""},
            "line_add_friend": {"is_active": False, "keyword": "", "add_friend_url": ""},
            "line_add_friend_access_token": "",
        },
        headers=headers,
    )
    assert resp.status_code == 200, f"Publish failed: {resp.status_code} {resp.text[:300]}"
    data = resp.json()["data"]
    url = f"https://note.com/flow_theory/n/{data['key']}"
    print(f"  ✅ Published: {url}")
    return url


def main():
    dry_run = "--dry" in sys.argv
    
    # Specific chapter?
    ch_override = None
    for i, arg in enumerate(sys.argv):
        if arg == "--ch" and i + 1 < len(sys.argv):
            ch_override = int(sys.argv[i + 1])
    
    state = load_state()
    ch_idx = ch_override if ch_override is not None else state["next_chapter"]
    
    if ch_idx >= len(CHAPTERS):
        print("全章投稿完了！")
        return
    
    ch = CHAPTERS[ch_idx]
    print(f"=== 章 {ch_idx}: {ch['title']} ===")
    
    # Extract text
    body_text = extract_chapter(ch)
    html_body = text_to_html(body_text)
    print(f"  Text: {len(body_text)} chars, HTML: {len(html_body)} chars")
    
    if dry_run:
        print(f"  [DRY RUN] Would post: {ch['title']}")
        print(f"  First 200 chars: {body_text[:200]}")
        return
    
    # Generate eyecatch
    print("  Generating eyecatch...")
    eyecatch_data, eyecatch_path = generate_eyecatch(ch_idx)
    print(f"  Eyecatch: {eyecatch_path}")
    
    # Post
    print("  Posting to note.com...")
    url = post_to_note(ch["title"], html_body, len(body_text), eyecatch_data, ch_idx)
    
    # Update state
    state["next_chapter"] = ch_idx + 1
    state["posted"].append({
        "chapter": ch_idx,
        "title": ch["title"],
        "url": url,
        "posted_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    })
    save_state(state)
    print(f"  State saved. Next: chapter {ch_idx + 1}")


if __name__ == "__main__":
    main()
