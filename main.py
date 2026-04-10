# -*- coding: utf-8 -*-
"""
Resume Portfolio Generator - FastAPI Backend
4 templates, project modal popup, intro section, real links
"""
import os, json, sqlite3, hashlib, re
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from groq import Groq
import pdfplumber, io

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

app = FastAPI(title="Resume Portfolio Generator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = Path(__file__).parent / "db" / "portfolios.db"
DB_PATH.parent.mkdir(exist_ok=True)

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS portfolios (
            id TEXT PRIMARY KEY, name TEXT, resume_text TEXT,
            sections TEXT, portfolio_html TEXT, created_at TEXT)""")
        conn.commit()
init_db()

# ── PDF extraction ────────────────────────────────────────────
def extract_from_pdf(b: bytes) -> tuple:
    text_parts, urls = [], set()
    url_re = re.compile(r'https?://[^\s\)\]\'"<>]+|github\.com/[^\s\)\]\'"<>]+|linkedin\.com/in/[^\s\)\]\'"<>]+')
    with pdfplumber.open(io.BytesIO(b)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
            for m in url_re.findall(t):
                urls.add(m.strip().rstrip(".,;)"))
            if page.hyperlinks:
                for lk in page.hyperlinks:
                    uri = lk.get("uri", "")
                    if uri: urls.add(uri.strip().rstrip(".,;)"))
    return "\n".join(text_parts), list(urls)

def extract_from_txt(b: bytes) -> tuple:
    text = b.decode("utf-8", errors="replace")
    url_re = re.compile(r'https?://[^\s\)\]\'"<>]+|github\.com/[^\s\)\]\'"<>]+')
    return text, list(set(m.strip().rstrip(".,;)") for m in url_re.findall(text)))

def clean_url(url):
    if not url or not isinstance(url, str): return ""
    url = url.strip().rstrip("/.,;)")
    if not url.startswith("http"): url = "https://" + url
    domain = url.replace("https://","").replace("http://","").split("/")[0]
    return url if "." in domain and len(domain) > 3 else ""

def validate_links(data, found_urls):
    def verify(url):
        url = clean_url(url)
        if not url: return ""
        if not found_urls: return url
        for fu in found_urls:
            fu2 = clean_url(fu)
            if url == fu2 or url in fu2 or fu2 in url: return url
        return ""
    lk = data.get("links", {})
    lk["github"]    = verify(lk.get("github",""))
    lk["linkedin"]  = verify(lk.get("linkedin",""))
    lk["portfolio"] = verify(lk.get("portfolio",""))
    em = lk.get("email","").strip()
    lk["email"] = em if "@" in em else ""
    data["links"] = lk
    for sec in data.get("sections",[]):
        if sec.get("type") == "cards":
            for item in sec.get("content",{}).get("items",[]):
                item["github"] = verify(item.get("github",""))
                item["demo"]   = verify(item.get("demo",""))
    return data

IMAGE_SETS = {
    "developer": ["https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=900&q=80","https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=900&q=80","https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=900&q=80","https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=900&q=80","https://images.unsplash.com/photo-1537432376769-00f5c2f4c8d2?w=900&q=80"],
    "designer":  ["https://images.unsplash.com/photo-1561070791-2526d30994b5?w=900&q=80","https://images.unsplash.com/photo-1572044162444-ad60f128bdea?w=900&q=80","https://images.unsplash.com/photo-1558655146-9f40138edfeb?w=900&q=80"],
    "data":      ["https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=900&q=80","https://images.unsplash.com/photo-1543286386-713bdd548da4?w=900&q=80","https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?w=900&q=80"],
    "business":  ["https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=900&q=80","https://images.unsplash.com/photo-1521791136064-7986c2920216?w=900&q=80","https://images.unsplash.com/photo-1497366216548-37526070297c?w=900&q=80"],
    "default":   ["https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?w=900&q=80","https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=900&q=80","https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=900&q=80"],
}

def get_images(field, n=6):
    f = field.lower()
    if any(k in f for k in ["develop","engineer","code","software","web","backend","frontend","program"]): pool = IMAGE_SETS["developer"]
    elif any(k in f for k in ["design","ui","ux","graphic","visual"]): pool = IMAGE_SETS["designer"]
    elif any(k in f for k in ["data","ml","ai","analyst","research","science"]): pool = IMAGE_SETS["data"]
    elif any(k in f for k in ["business","manage","market","finance","sales"]): pool = IMAGE_SETS["business"]
    else: pool = IMAGE_SETS["default"]
    return (pool * 4)[:n]

PALETTES = [
    ("midnight","#03070f","#060d1a","#0a1525","#60a5fa","#818cf8","#e2e8f0","#4b6080","#1a2a40"),
    ("teal",    "#02100e","#041a16","#072420","#2dd4bf","#34d399","#e0fdf4","#3a7a6a","#0a3028"),
    ("violet",  "#07030f","#0e0520","#150a2e","#c084fc","#e879f9","#faf5ff","#7a5fa0","#200a40"),
    ("rose",    "#0f0407","#1a070e","#260a14","#fb7185","#f472b6","#fff1f2","#9a4060","#380a18"),
    ("amber",   "#0c0800","#1a1200","#261b00","#fbbf24","#f59e0b","#fffbeb","#806020","#302000"),
    ("emerald", "#020c06","#041810","#071f12","#34d399","#a3e635","#ecfdf5","#2a6a4a","#0a3020"),
    ("slate",   "#080d14","#0f1724","#131e2e","#38bdf8","#6366f1","#e2e8f0","#4a6080","#1a2840"),
    ("coral",   "#0f0500","#1a0c00","#261200","#fb923c","#fbbf24","#fff7ed","#804020","#301800"),
    ("crimson", "#0f0206","#1a040c","#260612","#f43f5e","#fb7185","#fff1f2","#903050","#380010"),
    ("arctic",  "#04080f","#080f1c","#0d1828","#67e8f9","#a5f3fc","#ecfeff","#3a7a90","#0a2030"),
]

def pick_theme(name, tagline):
    seed = int(hashlib.md5((name+tagline).encode()).hexdigest(), 16)
    p = PALETTES[seed % len(PALETTES)]
    return dict(zip(["name","bg","surface","card","accent","accent2","text","muted","border"], p))

def pick_template(name):
    return int(hashlib.md5(name.encode()).hexdigest(), 16) % 4

SYSTEM_PROMPT = """You are a world-class portfolio strategist and UX writer.
Transform the resume into a creative, unique portfolio JSON.

FIELD: developer | designer | data | business | creative | student

SECTION NAMES - never generic:
- Developer: "What I Ship", "My Stack", "Where I've Worked"
- Designer: "Selected Work", "Design Thinking", "My Toolbox"
- Data/ML: "Research & Projects", "Technical Arsenal", "Impact by Numbers"
- Student: "What I'm Building", "Learning Path", "Next Chapter"
- Business: "What I Drive", "Case Studies", "Results"

WRITING: first person, confident, specific, no buzzwords.

LINKS (CRITICAL): Only URLs explicitly in the resume. Never guess. Empty string if not found.

Return ONLY valid JSON (no markdown):
{
  "name": "Full Name",
  "tagline": "Punchy one-liner",
  "field": "developer|designer|data|business|creative|student",
  "hero_image_query": "2-3 word query",
  "links": {"email": "", "github": "", "linkedin": "", "portfolio": ""},
  "sections": [
    {"id": "snake_case_id", "title": "Title", "type": "hero|intro|text|cards|list|timeline|skills", "content": {}}
  ]
}

Content shapes:
- hero: {"headline": str, "sub": str, "cta": str}
- intro: {"greeting": str, "body": str, "highlights": ["fact1","fact2","fact3"]}
- text: {"body": str}
- cards: {"items": [{"title":str,"subtitle":str,"desc":str,"tags":[str],"image_query":str,"github":"","demo":""}]}
- list: {"items": [{"label":str,"detail":str}]}
- timeline: {"items": [{"year":str,"title":str,"place":str,"desc":str}]}
- skills: {"groups": [{"label":str,"items":[str]}]}

MANDATORY: hero first, intro second (3-4 sentences about who they are + 3 highlight facts like "3 years experience"), then other sections.
"""

def ai_analyze_resume(resume_text, found_urls):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key: raise ValueError("GROQ_API_KEY not found")
    client = Groq(api_key=api_key)
    ctx = ("\n\nEXTRACTED URLS (use only these):\n" + "\n".join(found_urls)) if found_urls else ""
    comp = client.chat.completions.create(
        model="llama-3.3-70b-versatile", max_tokens=4096, temperature=0.8,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Resume:\n\n" + resume_text + ctx},
        ],
    )
    raw = comp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
    return json.loads(raw)

# ── Shared section builder ────────────────────────────────────
def esc(s):
    """Escape quotes for HTML data attributes."""
    return str(s).replace('"', '&quot;').replace("'", "&#39;")

def build_card(item, acc, border, card_bg, img_url, style="rounded"):
    """Build a clickable project card with modal data attributes."""
    tags_html = "".join(
        '<span style="background:' + acc + '18;color:' + acc + ';padding:3px 10px;border-radius:5px;font-size:0.71rem;font-weight:700;margin:2px">' + t + '</span>'
        for t in item.get("tags", [])
    )
    gh = item.get("github", "")
    dm = item.get("demo", "")
    link_row = ""
    if gh:
        link_row += '<a href="' + gh + '" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="display:inline-flex;align-items:center;gap:5px;padding:6px 12px;background:' + acc + '18;border:1px solid ' + acc + '40;border-radius:7px;color:' + acc + ';text-decoration:none;font-size:0.74rem;font-weight:700">GitHub</a>'
    if dm:
        link_row += '<a href="' + dm + '" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="display:inline-flex;align-items:center;gap:5px;padding:6px 12px;background:' + acc + ';border-radius:7px;color:#000;text-decoration:none;font-size:0.74rem;font-weight:700">Live Demo</a>'
    if link_row:
        link_row = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">' + link_row + '</div>'

    radius = "border-radius:16px" if style == "rounded" else "border-radius:0"
    tags_data = json.dumps(item.get("tags", []))

    return (
        '<div style="background:' + card_bg + ';border:1px solid ' + border + ';' + radius + ';overflow:hidden;cursor:pointer;transition:transform .25s,border-color .25s,box-shadow .25s"'
        ' onmouseover="this.style.transform=\'translateY(-6px)\';this.style.borderColor=\'' + acc + '80\';this.style.boxShadow=\'0 20px 40px #00000050\'"'
        ' onmouseout="this.style.transform=\'\';this.style.borderColor=\'' + border + '\';this.style.boxShadow=\'\'"'
        ' onclick="showModal(\'' + esc(item["title"]) + '\',\'' + esc(item.get("subtitle","")) + '\',\'' + esc(item["desc"]) + '\',\'' + esc(tags_data) + '\',\'' + img_url + '\',\'' + gh + '\',\'' + dm + '\',\'' + acc + '\')">'
        '<div style="height:160px;background:url(\'' + img_url + '\') center/cover;position:relative">'
        '<div style="position:absolute;inset:0;background:linear-gradient(to bottom,transparent 40%,' + card_bg + 'dd)"></div>'
        '</div>'
        '<div style="padding:20px 22px 24px">'
        '<h3 style="color:#fff;font-size:1rem;font-weight:700;margin-bottom:5px;line-height:1.3">' + item["title"] + '</h3>'
        '<p style="color:' + acc + ';font-size:0.8rem;font-weight:600;margin-bottom:10px">' + item.get("subtitle","") + '</p>'
        '<p style="color:#94a3b8;font-size:0.88rem;line-height:1.65;margin-bottom:12px">' + item["desc"] + '</p>'
        '<div style="display:flex;flex-wrap:wrap;gap:4px">' + tags_html + '</div>'
        + link_row +
        '</div></div>'
    )

def build_intro(greeting, body, highlights, acc, acc2, border, card_bg, style="default"):
    if not highlights:
        highlights = ["Open to opportunities", "Passionate builder", "Fast learner"]
    if style == "glass":
        glass = "background:rgba(255,255,255,.05);backdrop-filter:blur(14px);border:1px solid rgba(255,255,255,.1);border-radius:16px"
        hl_html = "".join(
            '<div style="' + glass + ';padding:16px 20px;display:flex;align-items:center;gap:10px">'
            '<span style="width:8px;height:8px;background:' + acc + ';border-radius:50%;flex-shrink:0"></span>'
            '<p style="color:#fff;font-size:0.87rem;font-weight:600">' + h + '</p>'
            '</div>'
            for h in highlights
        )
        left = '<div style="' + glass + ';padding:32px"><p style="font-size:0.68rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:' + acc + ';margin-bottom:12px">About me</p><h2 style="font-size:1.9rem;font-weight:800;color:#fff;margin-bottom:14px;letter-spacing:-0.02em">' + (greeting or "Who I Am") + '</h2><div style="width:44px;height:3px;background:linear-gradient(90deg,' + acc + ',' + acc2 + ');border-radius:99px;margin-bottom:18px"></div><p style="color:#94a3b8;line-height:1.85;font-size:0.97rem">' + body + '</p></div>'
    else:
        hl_html = "".join(
            '<div style="padding:16px 18px;border:1px solid ' + border + ';border-radius:10px;display:flex;align-items:center;gap:10px">'
            '<span style="width:8px;height:8px;background:' + acc + ';border-radius:50%;flex-shrink:0"></span>'
            '<p style="color:#fff;font-size:0.87rem;font-weight:600">' + h + '</p>'
            '</div>'
            for h in highlights
        )
        left = '<div><p style="font-size:0.68rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:' + acc + ';margin-bottom:12px">About me</p><h2 style="font-size:1.9rem;font-weight:800;color:#fff;margin-bottom:14px;letter-spacing:-0.02em">' + (greeting or "Who I Am") + '</h2><div style="width:44px;height:2px;background:linear-gradient(90deg,' + acc + ',' + acc2 + ');margin-bottom:18px"></div><p style="color:#94a3b8;line-height:1.85;font-size:0.97rem">' + body + '</p></div>'
    return (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:start">'
        + left +
        '<div style="display:flex;flex-direction:column;gap:12px;padding-top:8px">' + hl_html + '</div>'
        '</div>'
    )

def build_skills(groups, acc, acc2, card_bg, border, txt):
    html = ""
    for grp in groups:
        pills = "".join(
            '<span style="display:inline-block;padding:8px 16px;border:1px solid ' + border + ';border-radius:8px;font-size:0.84rem;color:' + txt + ';margin:4px;cursor:default;transition:all .2s"'
            ' onmouseover="this.style.borderColor=\'' + acc + '\';this.style.color=\'' + acc + '\';this.style.background=\'' + acc + '12\'"'
            ' onmouseout="this.style.borderColor=\'' + border + '\';this.style.color=\'' + txt + '\';this.style.background=\'transparent\'">'
            + s + '</span>'
            for s in grp.get("items", [])
        )
        html += (
            '<div style="margin-bottom:32px">'
            '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">'
            '<div style="width:3px;height:16px;background:linear-gradient(180deg,' + acc + ',' + acc2 + ');border-radius:99px"></div>'
            '<span style="font-size:0.78rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:' + txt + '">' + grp.get("label","") + '</span>'
            '</div>'
            '<div style="display:flex;flex-wrap:wrap">' + pills + '</div>'
            '</div>'
        )
    return html

def build_timeline(items, acc, border, txt, muted):
    html = ""
    for item in items:
        html += (
            '<div style="display:grid;grid-template-columns:90px 1fr;gap:32px;padding:28px 0;border-bottom:1px solid ' + border + '">'
            '<div style="text-align:right;padding-top:4px">'
            '<span style="color:' + acc + ';font-size:0.84rem;font-weight:700">' + item.get("year","") + '</span>'
            '</div>'
            '<div style="position:relative;padding-left:22px">'
            '<div style="position:absolute;left:0;top:7px;width:9px;height:9px;background:' + acc + ';border-radius:50%;box-shadow:0 0 0 3px ' + acc + '30"></div>'
            '<h3 style="color:' + txt + ';font-size:1rem;font-weight:700;margin-bottom:4px">' + item.get("title","") + '</h3>'
            '<p style="color:' + acc + ';font-size:0.83rem;font-weight:600;margin-bottom:8px">' + item.get("place","") + '</p>'
            '<p style="color:' + muted + ';font-size:0.9rem;line-height:1.7">' + item.get("desc","") + '</p>'
            '</div></div>'
        )
    return html

def build_list(items, acc, border, txt, muted, card_bg):
    html = ""
    for item in items:
        html += (
            '<div style="display:flex;justify-content:space-between;align-items:center;padding:15px 22px;background:' + card_bg + ';border:1px solid ' + border + ';border-radius:10px;margin-bottom:8px;transition:border-color .2s"'
            ' onmouseover="this.style.borderColor=\'' + acc + '60\'"'
            ' onmouseout="this.style.borderColor=\'' + border + '\'">'
            '<span style="color:' + txt + ';font-weight:600">' + item.get("label","") + '</span>'
            '<span style="color:' + acc + ';font-size:0.86rem;font-weight:700;background:' + acc + '18;padding:3px 12px;border-radius:99px">' + item.get("detail","") + '</span>'
            '</div>'
        )
    return html

# ── Modal HTML (shared by all templates) ─────────────────────
MODAL_HTML = """
<div id="proj-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9999;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(8px)" onclick="if(event.target===this)closeModal()">
  <div style="background:#0f172a;border:1px solid #1e293b;border-radius:20px;max-width:660px;width:100%;max-height:88vh;overflow-y:auto;position:relative;transform:translateY(20px);transition:transform .3s" id="modal-box">
    <button onclick="closeModal()" style="position:absolute;top:14px;right:14px;width:34px;height:34px;background:rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.15);border-radius:50%;color:#fff;font-size:1rem;cursor:pointer;z-index:10;display:flex;align-items:center;justify-content:center">x</button>
    <div id="modal-img" style="width:100%;height:220px;background-size:cover;background-position:center;border-radius:18px 18px 0 0"></div>
    <div style="padding:28px 32px 36px">
      <p id="modal-label" style="font-size:0.68rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;margin-bottom:10px"></p>
      <h2 id="modal-title" style="font-size:1.55rem;font-weight:800;color:#f1f5f9;margin-bottom:8px;line-height:1.2;letter-spacing:-0.02em"></h2>
      <p id="modal-sub" style="font-size:0.87rem;font-weight:600;margin-bottom:14px"></p>
      <p id="modal-desc" style="font-size:0.95rem;line-height:1.8;color:#94a3b8;margin-bottom:22px"></p>
      <div id="modal-tags" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:22px"></div>
      <div id="modal-links" style="display:flex;gap:10px;flex-wrap:wrap"></div>
    </div>
  </div>
</div>
<script>
function showModal(title,sub,desc,tagsJson,img,gh,dm,acc){
  var m=document.getElementById('proj-modal');
  document.getElementById('modal-title').textContent=title;
  document.getElementById('modal-sub').textContent=sub;
  document.getElementById('modal-sub').style.color=acc;
  document.getElementById('modal-desc').textContent=desc;
  document.getElementById('modal-label').textContent='Project Details';
  document.getElementById('modal-label').style.color=acc;
  document.getElementById('modal-img').style.backgroundImage='url('+img+')';
  var tags=[];try{tags=JSON.parse(tagsJson);}catch(e){}
  document.getElementById('modal-tags').innerHTML=tags.map(function(t){return '<span style="background:'+acc+'20;color:'+acc+';padding:4px 12px;border-radius:6px;font-size:0.74rem;font-weight:700">'+t+'</span>';}).join('');
  var links='';
  if(gh)links+='<a href="'+gh+'" target="_blank" rel="noopener" style="padding:10px 20px;background:'+acc+'18;border:1px solid '+acc+'40;border-radius:9px;color:'+acc+';text-decoration:none;font-size:0.85rem;font-weight:700">GitHub</a>';
  if(dm)links+='<a href="'+dm+'" target="_blank" rel="noopener" style="padding:10px 20px;background:'+acc+';border-radius:9px;color:#000;text-decoration:none;font-size:0.85rem;font-weight:700">Live Demo</a>';
  document.getElementById('modal-links').innerHTML=links;
  m.style.display='flex';
  setTimeout(function(){document.getElementById('modal-box').style.transform='none';},10);
  document.body.style.overflow='hidden';
}
function closeModal(){
  document.getElementById('proj-modal').style.display='none';
  document.getElementById('modal-box').style.transform='translateY(20px)';
  document.body.style.overflow='';
}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeModal();});
</script>
"""

# ══════════════════════════════════════════════════════════════
# TEMPLATE 0 — Dark Minimal
# ══════════════════════════════════════════════════════════════
def render_t0(data, theme, images):
    acc, acc2 = theme["accent"], theme["accent2"]
    txt, muted, border = theme["text"], theme["muted"], theme["border"]
    card, bg = theme["card"], theme["bg"]
    links = data.get("links", {})
    name = data["name"]
    initials = "".join(w[0] for w in name.split()[:2]).upper()

    nav_items = "".join(
        '<a href="#' + s["id"] + '" style="color:' + muted + ';text-decoration:none;font-size:0.85rem;font-weight:500;transition:color .2s"'
        ' onmouseover="this.style.color=\'' + txt + '\'" onmouseout="this.style.color=\'' + muted + '\'">' + s["title"] + '</a>'
        for s in data["sections"] if s["type"] != "hero"
    )

    sections_html = ""
    for s in data["sections"]:
        sections_html += '<div id="' + s["id"] + '">' + render_section_t0(s, theme, images) + '</div>'

    fb = ""
    if links.get("email"): fb += '<a href="mailto:' + links["email"] + '" style="color:' + muted + ';text-decoration:none;font-size:0.88rem;transition:color .2s" onmouseover="this.style.color=\'' + acc + '\'" onmouseout="this.style.color=\'' + muted + '\'">Email</a>'
    if links.get("github"): fb += '<a href="' + links["github"] + '" target="_blank" rel="noopener" style="color:' + muted + ';text-decoration:none;font-size:0.88rem;transition:color .2s" onmouseover="this.style.color=\'' + acc + '\'" onmouseout="this.style.color=\'' + muted + '\'">GitHub</a>'
    if links.get("linkedin"): fb += '<a href="' + links["linkedin"] + '" target="_blank" rel="noopener" style="color:' + muted + ';text-decoration:none;font-size:0.88rem;transition:color .2s" onmouseover="this.style.color=\'' + acc + '\'" onmouseout="this.style.color=\'' + muted + '\'">LinkedIn</a>'
    if links.get("portfolio"): fb += '<a href="' + links["portfolio"] + '" target="_blank" rel="noopener" style="color:' + muted + ';text-decoration:none;font-size:0.88rem;transition:color .2s" onmouseover="this.style.color=\'' + acc + '\'" onmouseout="this.style.color=\'' + muted + '\'">Website</a>'

    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + name + """ -- Portfolio</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700;800&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}
body{font-family:'Inter',sans-serif;background:""" + bg + """;color:""" + txt + """;-webkit-font-smoothing:antialiased;overflow-x:hidden}
.wrap{max-width:920px;margin:0 auto;padding:0 40px}
nav{position:fixed;top:0;left:0;right:0;z-index:100;padding:22px 0;transition:all .3s}
nav.on{background:""" + bg + """f0;backdrop-filter:blur(18px);border-bottom:1px solid """ + border + """;padding:14px 0}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
::-webkit-scrollbar{width:2px}::-webkit-scrollbar-thumb{background:""" + acc + """;border-radius:99px}
</style></head><body>
<nav id="nav"><div class="wrap" style="display:flex;justify-content:space-between;align-items:center">
  <span style="font-family:'Sora',sans-serif;font-weight:700;color:""" + txt + """;font-size:0.95rem">""" + name + """</span>
  <div style="display:flex;gap:28px;align-items:center">""" + nav_items + """
    <a href="#contact" style="padding:8px 20px;border:1px solid """ + acc + """;color:""" + acc + """;border-radius:99px;text-decoration:none;font-size:0.82rem;font-weight:600">Contact</a>
  </div>
</div></nav>
<div style="padding-top:80px"><div class="wrap">""" + sections_html + """</div></div>
<footer style="border-top:1px solid """ + border + """;padding:44px 0;margin-top:80px">
  <div class="wrap" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
    <div>
      <p style="font-family:'Sora',sans-serif;font-weight:700;font-size:1rem;color:""" + txt + """;margin-bottom:4px">""" + name + """</p>
      <p style="color:""" + muted + """;font-size:0.84rem" id="contact">""" + data.get("tagline","") + """</p>
    </div>
    <div style="display:flex;gap:22px;flex-wrap:wrap">""" + fb + """</div>
  </div>
</footer>
""" + MODAL_HTML + """
<script>
const nav=document.getElementById('nav');
window.addEventListener('scroll',function(){nav.classList.toggle('on',scrollY>40);});
document.querySelectorAll('[id]').forEach(function(el){
  el.style.opacity='0';
  new IntersectionObserver(function(entries){entries.forEach(function(e){
    if(e.isIntersecting){e.target.style.animation='fadeUp .5s ease both';e.target.style.opacity='1';}
  });},{threshold:.08}).observe(el);
});
</script></body></html>"""

def render_section_t0(section, theme, images):
    t = section["type"]
    c = section["content"]
    acc, acc2 = theme["accent"], theme["accent2"]
    muted, card = theme["muted"], theme["card"]
    txt, border, bg = theme["text"], theme["border"], theme["bg"]
    sw = "padding:72px 0;border-bottom:1px solid " + border
    h2s = "font-family:'Sora',sans-serif;font-size:2rem;font-weight:800;color:" + txt + ";letter-spacing:-0.03em"
    lbl = "font-size:0.68rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:" + acc + ";display:block;margin-bottom:14px"

    if t == "hero":
        img = images[0] if images else ""
        return (
            '<section style="min-height:100vh;display:flex;align-items:center;position:relative;overflow:hidden">'
            '<div style="position:absolute;right:0;top:0;bottom:0;width:44%;background:url(\'' + img + '\') center/cover;opacity:0.18"></div>'
            '<div style="position:absolute;right:0;top:0;bottom:0;width:44%;background:linear-gradient(to right,' + bg + ',transparent)"></div>'
            '<div style="position:relative;z-index:1;max-width:580px">'
            '<p style="color:' + acc + ';font-size:0.74rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;margin-bottom:20px">* ' + c.get("sub","") + '</p>'
            '<h1 style="font-family:\'Sora\',sans-serif;font-size:clamp(2.8rem,6vw,4.5rem);font-weight:800;letter-spacing:-0.04em;line-height:1.05;color:' + txt + ';margin-bottom:28px">' + c.get("headline","") + '</h1>'
            '<div style="width:56px;height:2px;background:linear-gradient(90deg,' + acc + ',' + acc2 + ');margin-bottom:28px"></div>'
            '<div style="display:flex;gap:12px;flex-wrap:wrap">'
            '<a href="#contact" style="padding:13px 30px;background:linear-gradient(135deg,' + acc + ',' + acc2 + ');color:#000;border-radius:8px;font-weight:700;text-decoration:none;font-family:\'Sora\',sans-serif">' + c.get("cta","") + '</a>'
            '<a href="#" style="padding:13px 30px;border:1px solid ' + border + ';color:' + txt + ';border-radius:8px;font-weight:500;text-decoration:none">Resume</a>'
            '</div></div></section>'
        )

    if t == "intro":
        return '<section style="' + sw + '">' + build_intro(c.get("greeting",""), c.get("body",""), c.get("highlights",[]), acc, acc2, border, card) + '</section>'

    if t == "text":
        img = images[1] if len(images) > 1 else ""
        right = '<div style="border-radius:12px;height:260px;background:url(\'' + img + '\') center/cover;border:1px solid ' + border + '30"></div>' if img else ""
        cols = "1fr 1fr" if img else "1fr"
        return (
            '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<div style="display:grid;grid-template-columns:' + cols + ';gap:52px;align-items:center">'
            '<div><h2 style="' + h2s + ';margin-bottom:18px">' + section["title"] + '</h2>'
            '<div style="width:40px;height:2px;background:' + acc + ';margin-bottom:22px"></div>'
            '<p style="color:' + muted + ';line-height:1.9;font-size:1rem">' + c.get("body","") + '</p></div>'
            + right + '</div></section>'
        )

    if t == "cards":
        imgs = get_images(section.get("title",""), 6)
        cards_html = "".join(build_card(item, acc, border, card, imgs[i % len(imgs)]) for i, item in enumerate(c.get("items",[])))
        return (
            '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<h2 style="' + h2s + ';margin-bottom:36px">' + section["title"] + '</h2>'
            '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px">' + cards_html + '</div></section>'
        )

    if t == "skills":
        return (
            '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<h2 style="' + h2s + ';margin-bottom:36px">' + section["title"] + '</h2>'
            + build_skills(c.get("groups",[]), acc, acc2, card, border, txt) + '</section>'
        )

    if t == "timeline":
        return (
            '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<h2 style="' + h2s + ';margin-bottom:36px">' + section["title"] + '</h2>'
            + build_timeline(c.get("items",[]), acc, border, txt, muted) + '</section>'
        )

    if t == "list":
        return (
            '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<h2 style="' + h2s + ';margin-bottom:28px">' + section["title"] + '</h2>'
            + build_list(c.get("items",[]), acc, border, txt, muted, card) + '</section>'
        )
    return ""

# ══════════════════════════════════════════════════════════════
# TEMPLATE 1 — Glassmorphism
# ══════════════════════════════════════════════════════════════
def render_t1(data, theme, images):
    acc, acc2 = theme["accent"], theme["accent2"]
    txt, muted, border = theme["text"], theme["muted"], theme["border"]
    card, bg = theme["card"], theme["bg"]
    links = data.get("links", {})
    name = data["name"]
    initials = "".join(w[0] for w in name.split()[:2]).upper()

    nav_items = "".join(
        '<a href="#' + s["id"] + '" style="color:' + muted + ';text-decoration:none;font-size:0.86rem;font-weight:500;transition:color .2s"'
        ' onmouseover="this.style.color=\'' + txt + '\'" onmouseout="this.style.color=\'' + muted + '\'">' + s["title"] + '</a>'
        for s in data["sections"] if s["type"] != "hero"
    )

    sections_html = "".join(
        '<div id="' + s["id"] + '">' + render_section_t1(s, theme, images) + '</div>'
        for s in data["sections"]
    )

    fb = ""
    if links.get("email"): fb += '<a href="mailto:' + links["email"] + '" style="padding:9px 20px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:99px;color:' + txt + ';text-decoration:none;font-size:0.83rem;font-weight:600">Email</a>'
    if links.get("github"): fb += '<a href="' + links["github"] + '" target="_blank" rel="noopener" style="padding:9px 20px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:99px;color:' + txt + ';text-decoration:none;font-size:0.83rem;font-weight:600">GitHub</a>'
    if links.get("linkedin"): fb += '<a href="' + links["linkedin"] + '" target="_blank" rel="noopener" style="padding:9px 20px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:99px;color:' + txt + ';text-decoration:none;font-size:0.83rem;font-weight:600">LinkedIn</a>'

    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + name + """ -- Portfolio</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}
body{font-family:'Plus Jakarta Sans',sans-serif;background:""" + bg + """;color:""" + txt + """;-webkit-font-smoothing:antialiased;overflow-x:hidden}
.wrap{max-width:1020px;margin:0 auto;padding:0 36px}
.glass{background:rgba(255,255,255,.04);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,.08);border-radius:18px}
nav{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:100;width:calc(100% - 72px);max-width:960px}
.nav-inner{background:rgba(255,255,255,.05);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,.1);border-radius:14px;padding:13px 26px;display:flex;justify-content:space-between;align-items:center}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:none}}
::-webkit-scrollbar{width:2px}::-webkit-scrollbar-thumb{background:""" + acc + """;border-radius:99px}
</style></head><body>
<div style="position:fixed;inset:0;pointer-events:none;z-index:0">
  <div style="position:absolute;top:-20%;left:-10%;width:60%;height:60%;background:radial-gradient(circle,""" + acc + """18,transparent 65%);filter:blur(60px)"></div>
  <div style="position:absolute;bottom:-20%;right:-10%;width:50%;height:50%;background:radial-gradient(circle,""" + acc2 + """12,transparent 65%);filter:blur(60px)"></div>
</div>
<nav><div class="nav-inner">
  <div style="display:flex;align-items:center;gap:10px">
    <div style="width:32px;height:32px;background:linear-gradient(135deg,""" + acc + """,""" + acc2 + """);border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:0.76rem;color:#000">""" + initials + """</div>
    <span style="font-weight:700;font-size:0.9rem;color:""" + txt + """">""" + name + """</span>
  </div>
  <div style="display:flex;gap:22px;align-items:center">""" + nav_items + """
    <a href="#contact" style="padding:8px 18px;background:linear-gradient(135deg,""" + acc + """,""" + acc2 + """);color:#000;border-radius:99px;text-decoration:none;font-size:0.8rem;font-weight:700">Hire me</a>
  </div>
</div></nav>
<div style="padding-top:100px;position:relative;z-index:1"><div class="wrap">""" + sections_html + """</div></div>
<footer style="position:relative;z-index:1;border-top:1px solid rgba(255,255,255,.06);padding:44px 0;margin-top:60px">
  <div class="wrap" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
    <div>
      <p style="font-weight:700;font-size:1rem;color:""" + txt + """;margin-bottom:4px">""" + name + """</p>
      <p style="color:""" + muted + """;font-size:0.84rem" id="contact">""" + data.get("tagline","") + """</p>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap">""" + fb + """</div>
  </div>
</footer>
""" + MODAL_HTML + """
<script>
document.querySelectorAll('[id]').forEach(function(el){
  el.style.opacity='0';
  new IntersectionObserver(function(entries){entries.forEach(function(e){
    if(e.isIntersecting){e.target.style.animation='fadeUp .5s ease both';e.target.style.opacity='1';}
  });},{threshold:.08}).observe(el);
});
</script></body></html>"""

def render_section_t1(section, theme, images):
    t = section["type"]
    c = section["content"]
    acc, acc2 = theme["accent"], theme["accent2"]
    muted, card = theme["muted"], theme["card"]
    txt, border, bg = theme["text"], theme["border"], theme["bg"]
    glass = "background:rgba(255,255,255,.04);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,.08);border-radius:18px"
    sw = "padding:72px 0"
    h2s = "font-size:2rem;font-weight:800;color:" + txt + ";letter-spacing:-0.03em;font-family:'Plus Jakarta Sans',sans-serif"
    lbl = "font-size:0.68rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:" + acc + ";display:block;margin-bottom:14px"

    if t == "hero":
        img = images[0] if images else ""
        return (
            '<section style="min-height:100vh;display:flex;align-items:center;text-align:center;padding:60px 0">'
            '<div style="width:100%">'
            '<div style="display:inline-flex;align-items:center;gap:8px;' + glass + ';padding:7px 18px;margin-bottom:30px;border-radius:99px">'
            '<span style="width:6px;height:6px;background:' + acc + ';border-radius:50%;animation:pulse 2s infinite;display:inline-block"></span>'
            '<span style="color:' + acc + ';font-size:0.75rem;font-weight:700;letter-spacing:.1em">OPEN TO WORK</span>'
            '</div>'
            '<h1 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:clamp(2.8rem,8vw,5rem);font-weight:800;letter-spacing:-0.04em;line-height:1.05;color:' + txt + ';margin-bottom:22px">' + c.get("headline","") + '</h1>'
            '<p style="font-size:1.1rem;color:' + muted + ';max-width:540px;margin:0 auto 40px;line-height:1.75">' + c.get("sub","") + '</p>'
            '<div style="display:flex;gap:14px;justify-content:center;flex-wrap:wrap">'
            '<a href="#contact" style="padding:13px 32px;background:linear-gradient(135deg,' + acc + ',' + acc2 + ');color:#000;border-radius:12px;font-weight:700;text-decoration:none">' + c.get("cta","") + '</a>'
            '<a href="#" style="' + glass + ';padding:13px 32px;color:' + txt + ';border-radius:12px;font-weight:600;text-decoration:none">Resume</a>'
            '</div></div></section>'
        )

    if t == "intro":
        return '<section style="' + sw + '">' + build_intro(c.get("greeting",""), c.get("body",""), c.get("highlights",[]), acc, acc2, border, card, "glass") + '</section>'

    if t == "text":
        img = images[1] if len(images) > 1 else ""
        right = '<div style="border-radius:14px;height:260px;background:url(\'' + img + '\') center/cover;border:1px solid rgba(255,255,255,.08)"></div>' if img else ""
        return (
            '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<div style="display:grid;grid-template-columns:' + ("1fr 1fr" if img else "1fr") + ';gap:44px;align-items:center">'
            '<div style="' + glass + ';padding:32px"><h2 style="' + h2s + ';margin-bottom:14px">' + section["title"] + '</h2>'
            '<div style="width:44px;height:3px;background:linear-gradient(90deg,' + acc + ',' + acc2 + ');border-radius:99px;margin-bottom:18px"></div>'
            '<p style="color:' + muted + ';line-height:1.85;font-size:0.97rem">' + c.get("body","") + '</p></div>'
            + right + '</div></section>'
        )

    if t == "cards":
        imgs = get_images(section.get("title",""), 6)
        cards_html = "".join(build_card(item, acc, "rgba(255,255,255,.08)", card, imgs[i % len(imgs)]) for i, item in enumerate(c.get("items",[])))
        return (
            '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<h2 style="' + h2s + ';margin-bottom:34px">' + section["title"] + '</h2>'
            '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px">' + cards_html + '</div></section>'
        )

    if t == "skills":
        return (
            '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<h2 style="' + h2s + ';margin-bottom:34px">' + section["title"] + '</h2>'
            '<div style="' + glass + ';padding:32px">'
            + build_skills(c.get("groups",[]), acc, acc2, "transparent", "rgba(255,255,255,.1)", txt)
            + '</div></section>'
        )

    if t == "timeline":
        rows = "".join(
            '<div style="display:grid;grid-template-columns:80px 1fr;gap:28px;padding:26px;' + glass + ';margin-bottom:10px">'
            '<div style="text-align:center;padding-top:3px"><span style="color:' + acc + ';font-size:0.83rem;font-weight:700">' + item.get("year","") + '</span></div>'
            '<div><h3 style="color:' + txt + ';font-size:0.97rem;font-weight:700;margin-bottom:4px">' + item.get("title","") + '</h3>'
            '<p style="color:' + acc + ';font-size:0.81rem;font-weight:600;margin-bottom:8px">' + item.get("place","") + '</p>'
            '<p style="color:' + muted + ';font-size:0.89rem;line-height:1.7">' + item.get("desc","") + '</p></div></div>'
            for item in c.get("items",[])
        )
        return '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:28px">' + section["title"] + '</h2>' + rows + '</section>'

    if t == "list":
        return '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:24px">' + section["title"] + '</h2>' + build_list(c.get("items",[]), acc, "rgba(255,255,255,.08)", txt, muted, "rgba(255,255,255,.04)") + '</section>'
    return ""

# ══════════════════════════════════════════════════════════════
# TEMPLATE 2 — Sidebar
# ══════════════════════════════════════════════════════════════
def render_t2(data, theme, images):
    acc, acc2 = theme["accent"], theme["accent2"]
    txt, muted, border = theme["text"], theme["muted"], theme["border"]
    card, bg = theme["card"], theme["bg"]
    links = data.get("links", {})
    name = data["name"]
    initials = "".join(w[0] for w in name.split()[:2]).upper()

    side_links = "".join(
        '<a href="#' + s["id"] + '" style="display:flex;align-items:center;gap:10px;color:' + muted + ';text-decoration:none;font-size:0.84rem;font-weight:500;padding:8px 12px;border-radius:8px;transition:all .2s"'
        ' onmouseover="this.style.background=\'' + acc + '18\';this.style.color=\'' + acc + '\'"'
        ' onmouseout="this.style.background=\'transparent\';this.style.color=\'' + muted + '\'">'
        '<span style="width:5px;height:5px;background:' + acc + ';border-radius:50%;opacity:.5"></span>' + s["title"] + '</a>'
        for s in data["sections"] if s["type"] != "hero"
    )

    fb = ""
    if links.get("email"): fb += '<a href="mailto:' + links["email"] + '" style="color:' + muted + ';text-decoration:none;font-size:0.79rem;padding:6px 0;display:block;transition:color .2s" onmouseover="this.style.color=\'' + acc + '\'" onmouseout="this.style.color=\'' + muted + '\'">Email: ' + links["email"] + '</a>'
    if links.get("github"): fb += '<a href="' + links["github"] + '" target="_blank" rel="noopener" style="color:' + muted + ';text-decoration:none;font-size:0.79rem;padding:6px 0;display:block;transition:color .2s" onmouseover="this.style.color=\'' + acc + '\'" onmouseout="this.style.color=\'' + muted + '\'">GitHub</a>'
    if links.get("linkedin"): fb += '<a href="' + links["linkedin"] + '" target="_blank" rel="noopener" style="color:' + muted + ';text-decoration:none;font-size:0.79rem;padding:6px 0;display:block;transition:color .2s" onmouseover="this.style.color=\'' + acc + '\'" onmouseout="this.style.color=\'' + muted + '\'">LinkedIn</a>'

    hero = next((s for s in data["sections"] if s["type"] == "hero"), None)
    hero_html = render_section_t2(hero, theme, images) if hero else ""
    rest_html = "".join(
        '<div id="' + s["id"] + '">' + render_section_t2(s, theme, images) + '</div>'
        for s in data["sections"] if s["type"] != "hero"
    )

    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + name + """ -- Portfolio</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}
body{font-family:'DM Sans',sans-serif;background:""" + bg + """;color:""" + txt + """;-webkit-font-smoothing:antialiased;display:grid;grid-template-columns:276px 1fr;min-height:100vh}
aside{position:fixed;top:0;left:0;bottom:0;width:276px;background:""" + card + """;border-right:1px solid """ + border + """;padding:36px 22px;display:flex;flex-direction:column;overflow-y:auto}
main{margin-left:276px}
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
::-webkit-scrollbar{width:2px}::-webkit-scrollbar-thumb{background:""" + acc + """;border-radius:99px}
@media(max-width:768px){body{grid-template-columns:1fr}aside{position:relative;width:100%}main{margin-left:0}}
</style></head><body>
<aside>
  <div style="margin-bottom:28px">
    <div style="width:50px;height:50px;background:linear-gradient(135deg,""" + acc + """,""" + acc2 + """);border-radius:13px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1rem;color:#000;margin-bottom:13px">""" + initials + """</div>
    <h2 style="font-weight:700;font-size:0.98rem;color:""" + txt + """;margin-bottom:4px">""" + name + """</h2>
    <p style="color:""" + muted + """;font-size:0.77rem;line-height:1.5">""" + data.get("tagline","") + """</p>
  </div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:26px">
    <span style="width:7px;height:7px;background:""" + acc + """;border-radius:50%;animation:pulse 2s infinite;display:inline-block"></span>
    <span style="color:""" + acc + """;font-size:0.71rem;font-weight:700;letter-spacing:.08em">AVAILABLE</span>
  </div>
  <nav style="flex:1;display:flex;flex-direction:column;gap:2px">""" + side_links + """</nav>
  <div style="border-top:1px solid """ + border + """;padding-top:18px" id="contact">""" + fb + """</div>
</aside>
<main>
  """ + hero_html + """
  <div style="padding:0 44px 80px">""" + rest_html + """</div>
</main>
""" + MODAL_HTML + """
<script>
document.querySelectorAll('[id]').forEach(function(el){
  el.style.opacity='0';
  new IntersectionObserver(function(entries){entries.forEach(function(e){
    if(e.isIntersecting){e.target.style.animation='fadeUp .5s ease both';e.target.style.opacity='1';}
  });},{threshold:.08}).observe(el);
});
</script></body></html>"""

def render_section_t2(section, theme, images):
    t = section["type"]
    c = section["content"]
    acc, acc2 = theme["accent"], theme["accent2"]
    muted, card = theme["muted"], theme["card"]
    txt, border, bg = theme["text"], theme["border"], theme["bg"]
    sw = "padding:52px 0;border-bottom:1px solid " + border
    h2s = "font-family:'DM Serif Display',serif;font-size:1.85rem;font-weight:400;color:" + txt + ";letter-spacing:-0.02em"
    lbl = "font-size:0.65rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:" + acc + ";display:block;margin-bottom:10px"

    if t == "hero":
        img = images[0] if images else ""
        return (
            '<section style="min-height:68vh;background:url(\'' + img + '\') center/cover;position:relative;display:flex;align-items:flex-end;padding:52px 44px">'
            '<div style="position:absolute;inset:0;background:linear-gradient(to top,' + bg + ' 28%,' + bg + '80 55%,transparent)"></div>'
            '<div style="position:relative;z-index:1;max-width:580px">'
            '<h1 style="font-family:\'DM Serif Display\',serif;font-size:clamp(2.2rem,5vw,3.6rem);font-weight:400;color:' + txt + ';line-height:1.1;margin-bottom:14px">' + c.get("headline","") + '</h1>'
            '<p style="color:' + muted + ';font-size:1rem;margin-bottom:26px;line-height:1.7">' + c.get("sub","") + '</p>'
            '<a href="#contact" style="padding:12px 26px;background:linear-gradient(135deg,' + acc + ',' + acc2 + ');color:#000;border-radius:8px;font-weight:600;text-decoration:none">' + c.get("cta","") + '</a>'
            '</div></section>'
        )

    if t == "intro":
        hl = c.get("highlights", []) or ["Open to opportunities","Passionate builder","Fast learner"]
        hl_html = "".join('<div style="padding:12px 16px;border-left:3px solid ' + acc + ';background:' + acc + '08;border-radius:0 7px 7px 0;margin-bottom:8px"><p style="color:' + txt + ';font-size:0.84rem;font-weight:600">' + h + '</p></div>' for h in hl)
        return (
            '<section style="' + sw + '">'
            '<span style="' + lbl + '">About me</span>'
            '<h2 style="' + h2s + ';margin-bottom:14px">' + (c.get("greeting","") or "Who I Am") + '</h2>'
            '<div style="width:36px;height:2px;background:' + acc + ';margin-bottom:18px"></div>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:32px;align-items:start">'
            '<p style="color:' + muted + ';line-height:1.9;font-size:0.96rem">' + c.get("body","") + '</p>'
            '<div>' + hl_html + '</div>'
            '</div></section>'
        )

    if t == "text":
        return '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:14px">' + section["title"] + '</h2><div style="width:36px;height:2px;background:' + acc + ';margin-bottom:18px"></div><p style="color:' + muted + ';line-height:1.9;font-size:0.96rem;max-width:660px">' + c.get("body","") + '</p></section>'

    if t == "cards":
        imgs = get_images(section.get("title",""), 6)
        cards_html = "".join(build_card(item, acc, border, card, imgs[i % len(imgs)]) for i, item in enumerate(c.get("items",[])))
        return '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:28px">' + section["title"] + '</h2><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px">' + cards_html + '</div></section>'

    if t == "skills":
        return '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:28px">' + section["title"] + '</h2>' + build_skills(c.get("groups",[]), acc, acc2, card, border, txt) + '</section>'

    if t == "timeline":
        return '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:28px">' + section["title"] + '</h2>' + build_timeline(c.get("items",[]), acc, border, txt, muted) + '</section>'

    if t == "list":
        return '<section style="' + sw + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:22px">' + section["title"] + '</h2>' + build_list(c.get("items",[]), acc, border, txt, muted, card) + '</section>'
    return ""

# ══════════════════════════════════════════════════════════════
# TEMPLATE 3 — Bold Magazine
# ══════════════════════════════════════════════════════════════
def render_t3(data, theme, images):
    acc, acc2 = theme["accent"], theme["accent2"]
    txt, muted, border = theme["text"], theme["muted"], theme["border"]
    card, bg = theme["card"], theme["bg"]
    links = data.get("links", {})
    name = data["name"]
    initials = "".join(w[0] for w in name.split()[:2]).upper()
    field = data.get("field","").upper()

    nav_items = "".join(
        '<a href="#' + s["id"] + '" style="color:' + muted + ';text-decoration:none;font-size:0.83rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase;transition:color .2s"'
        ' onmouseover="this.style.color=\'' + acc + '\'" onmouseout="this.style.color=\'' + muted + '\'">' + s["title"] + '</a>'
        for s in data["sections"] if s["type"] != "hero"
    )

    sections_html = "".join(
        '<div id="' + s["id"] + '">' + render_section_t3(s, theme, images, field) + '</div>'
        for s in data["sections"]
    )

    fb = ""
    if links.get("email"): fb += '<a href="mailto:' + links["email"] + '" style="padding:11px 22px;border:2px solid ' + border + ';color:' + txt + ';text-decoration:none;font-size:0.83rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;transition:all .2s" onmouseover="this.style.borderColor=\'' + acc + '\';this.style.color=\'' + acc + '\'" onmouseout="this.style.borderColor=\'' + border + '\';this.style.color=\'' + txt + '\'">EMAIL</a>'
    if links.get("github"): fb += '<a href="' + links["github"] + '" target="_blank" rel="noopener" style="padding:11px 22px;border:2px solid ' + border + ';color:' + txt + ';text-decoration:none;font-size:0.83rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;transition:all .2s" onmouseover="this.style.borderColor=\'' + acc + '\';this.style.color=\'' + acc + '\'" onmouseout="this.style.borderColor=\'' + border + '\';this.style.color=\'' + txt + '\'">GITHUB</a>'
    if links.get("linkedin"): fb += '<a href="' + links["linkedin"] + '" target="_blank" rel="noopener" style="padding:11px 22px;border:2px solid ' + border + ';color:' + txt + ';text-decoration:none;font-size:0.83rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;transition:all .2s" onmouseover="this.style.borderColor=\'' + acc + '\';this.style.color=\'' + acc + '\'" onmouseout="this.style.borderColor=\'' + border + '\';this.style.color=\'' + txt + '\'">LINKEDIN</a>'

    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + name + """ -- Portfolio</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}
body{font-family:'Space Grotesk',sans-serif;background:""" + bg + """;color:""" + txt + """;-webkit-font-smoothing:antialiased;overflow-x:hidden}
.wrap{max-width:1100px;margin:0 auto;padding:0 40px}
nav{position:fixed;top:0;left:0;right:0;z-index:100;border-bottom:1px solid """ + border + """;background:""" + bg + """}
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
::-webkit-scrollbar{width:2px}::-webkit-scrollbar-thumb{background:""" + acc + """;border-radius:0}
</style></head><body>
<nav><div class="wrap" style="display:flex;justify-content:space-between;align-items:center;padding-top:16px;padding-bottom:16px">
  <div style="display:flex;align-items:center;gap:12px">
    <div style="width:32px;height:32px;background:""" + acc + """;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:0.78rem;color:#000;font-family:'Space Mono',monospace">""" + initials + """</div>
    <span style="font-weight:600;font-size:0.9rem;color:""" + txt + """;letter-spacing:.02em">""" + name + """</span>
  </div>
  <div style="display:flex;gap:26px;align-items:center">""" + nav_items + """
    <a href="#contact" style="padding:8px 18px;background:""" + acc + """;color:#000;text-decoration:none;font-size:0.79rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase">HIRE ME</a>
  </div>
</div></nav>
<div style="padding-top:66px">""" + sections_html + """</div>
<footer style="border-top:2px solid """ + border + """;padding:44px 0" id="contact">
  <div class="wrap" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:20px">
    <div>
      <p style="font-family:'Space Mono',monospace;font-size:1.1rem;color:""" + txt + """;margin-bottom:5px">""" + name + """</p>
      <p style="color:""" + muted + """;font-size:0.87rem">""" + data.get("tagline","") + """</p>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">""" + fb + """</div>
  </div>
</footer>
""" + MODAL_HTML + """
<script>
document.querySelectorAll('[id]').forEach(function(el){
  el.style.opacity='0';
  new IntersectionObserver(function(entries){entries.forEach(function(e){
    if(e.isIntersecting){e.target.style.animation='fadeUp .5s ease both';e.target.style.opacity='1';}
  });},{threshold:.06}).observe(el);
});
</script></body></html>"""

def render_section_t3(section, theme, images, field=""):
    t = section["type"]
    c = section["content"]
    acc, acc2 = theme["accent"], theme["accent2"]
    muted, card = theme["muted"], theme["card"]
    txt, border, bg = theme["text"], theme["border"], theme["bg"]
    wrap = "max-width:1100px;margin:0 auto;padding:0 40px"
    sw = "padding:76px 0;border-bottom:1px solid " + border
    h2s = "font-size:2.3rem;font-weight:700;color:" + txt + ";letter-spacing:-0.03em;font-family:'Space Grotesk',sans-serif"
    lbl = "font-family:'Space Mono',monospace;font-size:0.64rem;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:" + acc + ";display:block;margin-bottom:14px"

    if t == "hero":
        img = images[0] if images else ""
        return (
            '<section style="position:relative;min-height:100vh;overflow:hidden">'
            '<div style="position:absolute;inset:0;background:url(\'' + img + '\') center/cover"></div>'
            '<div style="position:absolute;inset:0;background:linear-gradient(to right,' + bg + ' 44%,transparent 84%)"></div>'
            '<div style="position:absolute;inset:0;background:linear-gradient(to top,' + bg + ' 0%,transparent 38%)"></div>'
            '<div style="position:relative;z-index:1;display:flex;align-items:center;min-height:100vh">'
            '<div style="' + wrap + '">'
            '<p style="font-family:\'Space Mono\',monospace;font-size:0.68rem;letter-spacing:.2em;color:' + acc + ';text-transform:uppercase;margin-bottom:18px">-- ' + field + ' PORTFOLIO</p>'
            '<h1 style="font-family:\'Space Grotesk\',sans-serif;font-size:clamp(3rem,9vw,6.5rem);font-weight:700;letter-spacing:-0.05em;line-height:0.95;color:' + txt + ';margin-bottom:28px">' + c.get("headline","") + '</h1>'
            '<p style="font-size:1.05rem;color:' + muted + ';max-width:460px;line-height:1.75;margin-bottom:36px">' + c.get("sub","") + '</p>'
            '<div style="display:flex;gap:10px;flex-wrap:wrap">'
            '<a href="#contact" style="padding:13px 30px;background:' + acc + ';color:#000;text-decoration:none;font-weight:700;letter-spacing:.04em;font-size:0.88rem">' + c.get("cta","").upper() + '</a>'
            '<a href="#" style="padding:13px 30px;border:2px solid ' + border + ';color:' + txt + ';text-decoration:none;font-weight:600;font-size:0.88rem">RESUME</a>'
            '</div></div></div></section>'
        )

    if t == "intro":
        hl = c.get("highlights", []) or ["Open to opportunities","Passionate builder","Fast learner"]
        hl_html = "".join('<div style="border:2px solid ' + border + ';padding:16px 20px"><p style="font-family:\'Space Mono\',monospace;color:' + acc + ';font-size:0.74rem;font-weight:700;letter-spacing:.08em">' + h + '</p></div>' for h in hl)
        return (
            '<section style="' + sw + '"><div style="' + wrap + '">'
            '<span style="' + lbl + '">About me</span>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:56px;align-items:start">'
            '<div><h2 style="' + h2s + ';margin-bottom:18px">' + (c.get("greeting","") or "Who I Am") + '</h2>'
            '<div style="width:48px;height:3px;background:' + acc + ';margin-bottom:22px"></div>'
            '<p style="color:' + muted + ';line-height:1.9;font-size:0.97rem">' + c.get("body","") + '</p></div>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;padding-top:8px">' + hl_html + '</div>'
            '</div></div></section>'
        )

    if t == "text":
        img = images[1] if len(images) > 1 else ""
        right = '<div style="height:280px;background:url(\'' + img + '\') center/cover;border:1px solid ' + border + '20"></div>' if img else ""
        return (
            '<section style="' + sw + '"><div style="' + wrap + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<div style="display:grid;grid-template-columns:' + ("1fr 1fr" if img else "1fr") + ';gap:56px;align-items:center">'
            '<div><h2 style="' + h2s + ';margin-bottom:22px">' + section["title"] + '</h2>'
            '<div style="width:44px;height:3px;background:' + acc + ';margin-bottom:22px"></div>'
            '<p style="color:' + muted + ';line-height:1.9;font-size:0.97rem">' + c.get("body","") + '</p></div>'
            + right + '</div></div></section>'
        )

    if t == "cards":
        imgs = get_images(section.get("title",""), 6)
        cards_html = "".join(build_card(item, acc, border, card, imgs[i % len(imgs)], "rounded") for i, item in enumerate(c.get("items",[])))
        return (
            '<section style="' + sw + '"><div style="' + wrap + '"><span style="' + lbl + '">' + section["title"] + '</span>'
            '<h2 style="' + h2s + ';margin-bottom:36px">' + section["title"] + '</h2>'
            '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px">' + cards_html + '</div></div></section>'
        )

    if t == "skills":
        grps = c.get("groups",[])
        html = ""
        for grp in grps:
            pills = "".join(
                '<span style="display:inline-block;padding:7px 16px;border:1px solid ' + border + ';font-size:0.83rem;color:' + txt + ';margin:4px;transition:all .2s;font-family:\'Space Grotesk\',sans-serif;cursor:default"'
                ' onmouseover="this.style.borderColor=\'' + acc + '\';this.style.color=\'' + acc + '\';this.style.background=\'' + acc + '10\'"'
                ' onmouseout="this.style.borderColor=\'' + border + '\';this.style.color=\'' + txt + '\';this.style.background=\'transparent\'">' + s + '</span>'
                for s in grp.get("items",[])
            )
            html += '<div style="margin-bottom:26px"><p style="font-family:\'Space Mono\',monospace;font-size:0.63rem;letter-spacing:.15em;text-transform:uppercase;color:' + muted + ';margin-bottom:10px">' + grp.get("label","") + '</p><div>' + pills + '</div></div>'
        return '<section style="' + sw + '"><div style="' + wrap + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:32px">' + section["title"] + '</h2>' + html + '</div></section>'

    if t == "timeline":
        rows = "".join(
            '<div style="display:grid;grid-template-columns:96px 1fr;gap:36px;padding:26px 0;border-bottom:1px solid ' + border + '">'
            '<span style="font-family:\'Space Mono\',monospace;color:' + acc + ';font-size:0.83rem;font-weight:700;padding-top:2px">' + item.get("year","") + '</span>'
            '<div><h3 style="font-family:\'Space Grotesk\',sans-serif;font-size:0.98rem;font-weight:700;color:' + txt + ';margin-bottom:4px">' + item.get("title","") + '</h3>'
            '<p style="font-family:\'Space Mono\',monospace;color:' + acc + ';font-size:0.74rem;margin-bottom:8px;letter-spacing:.04em">' + item.get("place","") + '</p>'
            '<p style="color:' + muted + ';font-size:0.89rem;line-height:1.7">' + item.get("desc","") + '</p></div></div>'
            for item in c.get("items",[])
        )
        return '<section style="' + sw + '"><div style="' + wrap + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:32px">' + section["title"] + '</h2>' + rows + '</div></section>'

    if t == "list":
        rows = "".join(
            '<div style="display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid ' + border + '">'
            '<span style="color:' + txt + ';font-weight:600">' + item.get("label","") + '</span>'
            '<span style="font-family:\'Space Mono\',monospace;color:' + acc + ';font-size:0.83rem">' + item.get("detail","") + '</span></div>'
            for item in c.get("items",[])
        )
        return '<section style="' + sw + '"><div style="' + wrap + '"><span style="' + lbl + '">' + section["title"] + '</span><h2 style="' + h2s + ';margin-bottom:26px">' + section["title"] + '</h2>' + rows + '</div></section>'
    return ""

# ── Dispatcher ────────────────────────────────────────────────
def build_portfolio_html(data):
    theme  = pick_theme(data["name"], data.get("tagline",""))
    tmpl   = pick_template(data["name"])
    images = get_images(data.get("field","default"), 8)
    if tmpl == 0: return render_t0(data, theme, images)
    if tmpl == 1: return render_t1(data, theme, images)
    if tmpl == 2: return render_t2(data, theme, images)
    return render_t3(data, theme, images)

# ── Routes ────────────────────────────────────────────────────
@app.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    content = await file.read()
    if file.filename.endswith(".pdf"):
        resume_text, found_urls = extract_from_pdf(content)
    elif file.filename.endswith((".txt",".md")):
        resume_text, found_urls = extract_from_txt(content)
    else:
        raise HTTPException(400, "Only PDF, TXT or MD supported")
    if len(resume_text.strip()) < 100:
        raise HTTPException(400, "Could not extract enough text")

    portfolio_id = hashlib.md5(resume_text.encode()).hexdigest()[:12]

    try:
        data = ai_analyze_resume(resume_text, found_urls)
        data = validate_links(data, found_urls)
    except Exception as e:
        raise HTTPException(500, f"AI analysis failed: {e}")

    html = build_portfolio_html(data)

    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO portfolios VALUES (?,?,?,?,?,?)",
            (portfolio_id, data["name"], resume_text, json.dumps(data["sections"]),
             html, datetime.utcnow().isoformat()))
        conn.commit()

    return {"id": portfolio_id, "name": data["name"], "tagline": data.get("tagline",""), "cached": False}

@app.get("/portfolio/{portfolio_id}", response_class=HTMLResponse)
async def get_portfolio(portfolio_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT portfolio_html FROM portfolios WHERE id=?", (portfolio_id,)).fetchone()
    if not row: raise HTTPException(404, "Portfolio not found")
    return row["portfolio_html"]

@app.get("/portfolios")
async def list_portfolios():
    with get_db() as conn:
        rows = conn.execute("SELECT id, name, created_at FROM portfolios ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

@app.get("/health")
async def health():
    return {"status": "ok"}