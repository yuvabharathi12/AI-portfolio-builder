"""
Resume Portfolio Generator — Streamlit 1.40.2 Frontend
"""
import streamlit as st
import requests
import time

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="Resume → Portfolio",
    page_icon="✦",
    layout="centered",
)

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #080d14; }
  [data-testid="stHeader"] { background: transparent; }
  .main > div { padding-top: 2rem; }

  .hero { text-align: center; padding: 52px 0 36px; }
  .hero h1 {
    font-size: 2.8rem; font-weight: 800;
    background: linear-gradient(135deg, #38bdf8, #818cf8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 14px;
  }
  .hero p { color: #64748b; font-size: 1.05rem; max-width: 480px; margin: 0 auto; line-height: 1.7; }

  .step-card {
    background: #0f1724; border: 1px solid #1e293b;
    border-radius: 12px; padding: 20px 22px; margin: 6px 0;
  }
  .step-num { color: #38bdf8; font-size: 0.72rem; font-weight: 700; letter-spacing:.1em; text-transform:uppercase; }
  .step-title { color: #e2e8f0; font-size: 0.95rem; font-weight: 600; margin: 5px 0 4px; }
  .step-desc { color: #475569; font-size: 0.84rem; line-height: 1.5; }

  .badge {
    display: inline-block; background: #38bdf818; color: #38bdf8;
    padding: 4px 14px; border-radius: 99px; font-size: 0.78rem; font-weight: 600;
    border: 1px solid #38bdf830;
  }

  .pcard {
    background: #0f1724; border: 1px solid #1e293b;
    border-radius: 10px; padding: 16px 20px; margin: 6px 0;
  }
  .pname { color: #e2e8f0; font-weight: 700; font-size: 0.95rem; }
  .pdate { color: #475569; font-size: 0.8rem; margin-top: 3px; }

  .progress-bar {
    height: 3px; background: linear-gradient(90deg, #38bdf8, #818cf8);
    border-radius: 99px; margin: 8px 0;
    animation: progress 30s linear forwards;
  }
  @keyframes progress { from { width: 0% } to { width: 100% } }
</style>
""", unsafe_allow_html=True)

def api_alive():
    try:
        return requests.get(f"{API_BASE}/health", timeout=2).status_code == 200
    except:
        return False

# ── Hero ──────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <h1>Resume → Portfolio</h1>
  <p>Upload your resume. Groq extracts your data. Claude designs a unique portfolio from scratch.</p>
</div>
""", unsafe_allow_html=True)

if not api_alive():
    st.error("⚠️ Backend not running. Start it with: `uvicorn main:app --reload --port 8000`")
    st.stop()

# ── How it works ──────────────────────────────────────────────
with st.expander("✦ How it works", expanded=False):
    cols = st.columns(3)
    steps = [
        ("01", "Extract", "Groq reads your resume and pulls out structured data — fast and accurate"),
        ("02", "Design", "Claude designs a completely unique HTML/CSS portfolio from scratch"),
        ("03", "Deploy", "Get a live link + downloadable HTML file instantly"),
    ]
    for col, (num, title, desc) in zip(cols, steps):
        col.markdown(f"""<div class="step-card">
          <div class="step-num">Step {num}</div>
          <div class="step-title">{title}</div>
          <div class="step-desc">{desc}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("---")

# ── Upload ────────────────────────────────────────────────────
st.markdown("### Upload your resume")
uploaded = st.file_uploader(
    "Drop resume here",
    type=["pdf", "txt", "md"],
    label_visibility="collapsed"
)

if uploaded:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f'<span class="badge">📄 {uploaded.name}</span>', unsafe_allow_html=True)
    with col2:
        go = st.button("✦ Generate", type="primary", use_container_width=True)

    if go:
        status_box = st.empty()
        progress = st.empty()

        steps_done = []
        def show_status(msg, done=False):
            steps_done.append(("✅" if done else "⏳") + " " + msg)
            status_box.markdown("\n\n".join(steps_done))

        show_status("Reading resume and extracting hyperlinks...")
        progress.markdown('<div class="progress-bar"></div>', unsafe_allow_html=True)

        try:
            files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")}

            # Longer timeout — Claude generation takes ~30-60s
            resp = requests.post(f"{API_BASE}/upload", files=files, timeout=180)

            if resp.status_code != 200:
                st.error(f"Error: {resp.text}")
                st.stop()

            data = resp.json()
            progress.empty()
            status_box.empty()

        except requests.Timeout:
            st.error("Timed out after 3 minutes. Try a shorter resume or check the backend terminal.")
            st.stop()
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

        # ── Success ───────────────────────────────────────────
        st.success(f"✦ **{data['name']}**'s portfolio is ready!")

        if data.get("tagline"):
            st.markdown(f'> *{data["tagline"]}*')

        portfolio_url = f"{API_BASE}/portfolio/{data['id']}"

        col_a, col_b = st.columns(2)
        with col_a:
            st.link_button("🌐 Open Portfolio", portfolio_url, use_container_width=True)
        with col_b:
            try:
                html_bytes = requests.get(portfolio_url, timeout=15).content
                safe_name = data['name'].replace(' ', '_').replace('/', '_')
                st.download_button(
                    "⬇️ Download HTML",
                    data=html_bytes,
                    file_name=f"{safe_name}_portfolio.html",
                    mime="text/html",
                    use_container_width=True,
                )
            except:
                st.warning("Could not prepare download — open the link above")

        st.markdown("### Preview")
        try:
            html_content = requests.get(portfolio_url, timeout=15).text
            st.components.v1.html(html_content, height=640, scrolling=True)
        except:
            st.info("Open the portfolio link above to view it in full.")

st.markdown("---")

# ── Past portfolios ───────────────────────────────────────────
st.markdown("### Past portfolios")
try:
    past = requests.get(f"{API_BASE}/portfolios", timeout=5).json()
    if not past:
        st.caption("No portfolios yet — upload a resume above.")
    else:
        for p in past[:10]:
            date = p.get("created_at","")[:10] or "—"
            col_x, col_y = st.columns([4, 1])
            with col_x:
                st.markdown(f"""<div class="pcard">
                  <div class="pname">{p['name']}</div>
                  <div class="pdate">{date}</div>
                </div>""", unsafe_allow_html=True)
            with col_y:
                st.link_button("View", f"{API_BASE}/portfolio/{p['id']}", use_container_width=True)
except:
    st.caption("Could not load past portfolios.")