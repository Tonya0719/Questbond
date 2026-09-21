"""Dispatch presentation helpers. Always escape customer and model content."""
from html import escape
import streamlit as st


def text(value):
    return escape(str(value if value is not None else 'Not provided'))


def stage(number, title):
    st.markdown(f'<div class="dispatch-stage" role="heading" aria-level="2"><span>{number}</span> {text(title)}</div>', unsafe_allow_html=True)


def stamp(label, description, tone='pending'):
    st.markdown(f'<section class="dispatch-stamp {tone}" role="status"><strong>{text(label)}</strong><p>{text(description)}</p></section>', unsafe_allow_html=True)


def apply_theme():
    st.sidebar.markdown('''<div class="side-brand"><div class="side-logo">M</div><div><strong>Mendigo</strong><span>Smart maintenance</span></div></div>''', unsafe_allow_html=True)
    choice = st.sidebar.selectbox('Appearance', ['System', 'Light', 'Dark'], key='dispatch_appearance')
    dark = '--bg:#111318;--canvas:#111318;--header:rgba(17,19,24,.76);--glow1:rgba(99,102,241,.24);--glow2:rgba(20,184,166,.14);--glow3:rgba(249,115,22,.10);--surface:#191C24;--surface2:#212530;--ink:#F9FAFB;--dim:#A7B0BE;--primary:#818CF8;--primary2:#6366F1;--amber:#FDBA74;--teal:#6EE7B7;--red:#FDA4AF;--line:#323744;--shadow:0 20px 35px -15px rgba(0,0,0,.45);'
    light = '--bg:#F7F6F2;--canvas:#F8F6F1;--header:rgba(248,246,241,.72);--glow1:rgba(167,139,250,.23);--glow2:rgba(45,212,191,.16);--glow3:rgba(251,146,60,.13);--surface:#FFFFFF;--surface2:#F9FAFB;--ink:#111827;--dim:#6B7280;--primary:#6366F1;--primary2:#4F46E5;--amber:#F59E0B;--teal:#059669;--red:#E11D48;--line:#E5E7EB;--shadow:0 20px 25px -5px rgba(17,24,39,.05),0 8px 10px -6px rgba(17,24,39,.04);'
    variables = dark if choice == 'Dark' else light
    system = f'@media(prefers-color-scheme:dark){{:root{{{dark}}}}}' if choice == 'System' else ''
    st.markdown('<style>@import url("https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL@20,400,0&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400&display=swap");'
        + ':root{' + variables + '}' + system + '''
        *{box-sizing:border-box}.stApp,[data-testid="stHeader"]{color:var(--ink)}
        [data-testid="stHeader"]{background:var(--header);backdrop-filter:blur(14px);border-bottom:1px solid color-mix(in srgb,var(--line) 60%,transparent)}
        .stApp{font-family:'Plus Jakarta Sans',sans-serif;background-color:var(--canvas);background-image:radial-gradient(circle at 7% 5%,var(--glow1) 0,transparent 30rem),radial-gradient(circle at 96% 24%,var(--glow2) 0,transparent 28rem),radial-gradient(circle at 68% 92%,var(--glow3) 0,transparent 30rem),linear-gradient(135deg,color-mix(in srgb,var(--canvas) 96%,#fff) 0%,color-mix(in srgb,var(--canvas) 91%,#EEF2FF) 48%,color-mix(in srgb,var(--canvas) 93%,#ECFDF5) 100%);background-attachment:fixed}
        h1,h2,h3,label,.dispatch-brand{font-family:'Plus Jakarta Sans',sans-serif;color:var(--ink);letter-spacing:-.02em}
        p{line-height:1.65}.material-symbols-rounded{font-family:'Material Symbols Rounded';font-size:20px;vertical-align:-4px}
        [data-testid="stSidebar"]{background:color-mix(in srgb,var(--surface) 76%,var(--bg));border-right:1px solid var(--line)}
        [data-testid="stSidebar"] *{color:var(--ink)}
        [data-testid="stSidebar"]>div:first-child{padding-top:1.35rem}
        .side-brand{display:flex;align-items:center;gap:12px;margin:0 0 24px;padding:4px}
        .side-logo{width:42px;height:42px;border-radius:14px;display:grid;place-items:center;background:linear-gradient(135deg,#818CF8,#4F46E5);color:white!important;font-weight:800;font-size:20px;box-shadow:0 8px 18px rgba(99,102,241,.28)}
        .side-brand strong{display:block;font-size:18px;letter-spacing:-.03em}.side-brand span{display:block;color:var(--dim)!important;font-size:11px;margin-top:2px}
        .block-container{padding:4.75rem 2rem 4rem;max-width:1600px}
        .dispatch-top{display:flex;align-items:baseline;gap:24px;border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:20px;flex-wrap:wrap}
        .dispatch-brand{font-size:30px;font-weight:800}.dispatch-muted{color:var(--dim)}
        .dispatch-stage{font-weight:700;font-size:20px!important;display:flex;gap:12px;align-items:center;margin:24px 0 12px}
        .dispatch-stage>span{color:var(--primary);font-size:14px;border:1px solid color-mix(in srgb,var(--primary) 30%,transparent);background:color-mix(in srgb,var(--primary) 10%,transparent);padding:5px 10px;border-radius:999px}
        .dispatch-request,.dispatch-stamp{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px;margin:12px 0;white-space:pre-wrap;box-shadow:var(--shadow)}
        .dispatch-request p,.dispatch-stamp p,.dispatch-explanation{max-width:64ch;line-height:1.65}
        .dispatch-stamp{border-left:5px solid var(--amber)}.dispatch-stamp strong{font-size:20px;color:var(--amber)}
        .dispatch-stamp.resolved{border-color:var(--teal)}.dispatch-stamp.resolved strong{color:var(--teal)}
        .dispatch-stamp.conflict{border-color:var(--red)}.dispatch-stamp.conflict strong{color:var(--red)}
        .dispatch-fields{display:grid;grid-template-columns:150px 1fr;gap:10px 20px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:var(--shadow)}
        .dispatch-fields dt{color:var(--dim)}.dispatch-fields dd{margin:0;overflow-wrap:anywhere}
        .dispatch-table{width:100%;border-collapse:collapse;background:var(--surface);font-size:14px}
        .dispatch-table td,.dispatch-table th{text-align:left;padding:12px;border-bottom:1px solid var(--line);vertical-align:top}
        .dispatch-table th{color:var(--dim);font-weight:500}.dispatch-scroll{overflow-x:auto}
        .dispatch-pill{display:inline-block;border:1px solid currentColor;padding:4px 9px;font-size:12px;border-radius:999px;white-space:nowrap}
        .pending{color:var(--amber)}.resolved{color:var(--teal)}.conflict{color:var(--red)}
        .dispatch-log{background:var(--surface2);padding:16px;border-left:3px solid var(--line);font-family:'IBM Plex Mono',monospace;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}
        .dispatch-detail{animation:dispatch-enter .22s ease-out}@keyframes dispatch-enter{from{opacity:.5;transform:translateY(5px)}to{opacity:1;transform:none}}
        .stButton button,.stDownloadButton button,.stFormSubmitButton button{min-height:46px;background:var(--surface);color:var(--ink);border:1.5px solid var(--line);border-radius:12px;box-shadow:0 1px 2px rgba(0,0,0,.03);font-weight:600;transition:all 150ms ease}
        .stButton button:hover,.stDownloadButton button:hover{border-color:var(--primary);color:var(--primary);transform:translateY(-1px);box-shadow:0 8px 18px rgba(99,102,241,.12)}
        button[kind="primary"],.stFormSubmitButton button[kind="primary"]{background:linear-gradient(135deg,var(--primary),var(--primary2))!important;color:white!important;border:none!important;box-shadow:0 10px 20px rgba(99,102,241,.24)!important;justify-content:center}
        button[kind="primary"]:hover{filter:brightness(1.05);transform:translateY(-1px);box-shadow:0 14px 26px rgba(99,102,241,.3)!important}
        [data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{min-height:48px;background:var(--surface2)!important;color:var(--ink)!important;border:1.5px solid var(--line)!important;border-radius:12px!important;transition:all 150ms ease;box-shadow:none!important}
        [data-baseweb="input"] input,textarea{background:transparent!important;color:var(--ink)!important}
        [data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within,[data-baseweb="select"]>div:focus-within{background:var(--surface)!important;border-color:var(--primary)!important;box-shadow:0 0 0 3px rgba(99,102,241,.15)!important}
        [data-baseweb="textarea"],textarea{min-height:120px!important;resize:vertical!important}
        input::placeholder,textarea::placeholder{color:var(--dim)!important}
        label p{font-size:13px!important;font-weight:600!important;color:var(--ink)!important}
        .stButton button:focus-visible,.stDownloadButton button:focus-visible,.stFormSubmitButton button:focus-visible{outline:3px solid rgba(99,102,241,.3);outline-offset:3px}
        [data-testid="stCaptionContainer"]{color:var(--dim)}
        [data-testid="stExpander"]{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden}
        [data-testid="stAlert"]{border-radius:14px;border-width:1px;box-shadow:0 8px 18px rgba(17,24,39,.04)}
        [data-testid="stFileUploaderDropzone"]{background:var(--surface2);border:1.5px dashed color-mix(in srgb,var(--primary) 35%,var(--line));border-radius:16px;padding:18px;transition:all 150ms ease}
        [data-testid="stFileUploaderDropzone"]:hover{background:color-mix(in srgb,var(--primary) 5%,var(--surface));border-color:var(--primary)}
        div[data-testid="stForm"]{background:var(--surface);border:1px solid rgba(229,231,235,.9);border-radius:24px;padding:30px 32px 34px;box-shadow:var(--shadow)}
        .customer-hero{max-width:860px;margin:4px auto 24px;text-align:center}.customer-hero .eyebrow{display:inline-flex;align-items:center;gap:7px;padding:7px 11px;border-radius:999px;background:#EEF2FF;color:#4338CA;font-size:12px;font-weight:700;letter-spacing:.02em}
        .customer-hero h1{font-size:38px;line-height:1.14;margin:16px 0 8px;font-weight:800;letter-spacing:-.045em}.customer-hero h1 span{color:var(--primary)}
        .customer-hero p{font-size:15px;color:var(--dim);margin:0 auto;max-width:590px}
        .service-chips{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin:18px 0 0}.service-chip{font-size:12px;font-weight:600;padding:7px 10px;border-radius:999px}.mint{background:#ECFDF5;color:#065F46}.lavender{background:#EEF2FF;color:#3730A3}.peach{background:#FFF7ED;color:#9A3412}
        .form-section{display:flex;align-items:center;gap:9px;margin:2px 0 8px;color:var(--ink);font-size:15px;font-weight:700}.form-section:not(:first-child){margin-top:18px}.form-section span{width:30px;height:30px;border-radius:10px;background:#EEF2FF;color:#4F46E5;display:grid;place-items:center}
        .form-helper{color:var(--dim);font-size:12px;margin:-2px 0 10px}
        .request-hero{background:linear-gradient(135deg,#EEF2FF,#FAF5FF);border:1px solid #E0E7FF;border-radius:22px;padding:24px;margin:0 0 18px;color:#312E81;box-shadow:var(--shadow)}
        .request-hero .request-kicker{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#6366F1}.request-hero h2{font-size:24px;margin:7px 0 5px}.request-hero p{margin:0;color:#5B5F76}.request-id{font-family:'IBM Plex Mono',monospace;display:inline-block;margin-top:14px;padding:7px 10px;background:rgba(255,255,255,.75);border-radius:9px;font-size:12px;color:#4338CA}
        .permission-note{margin-top:12px;padding:11px 12px;border-radius:12px;background:color-mix(in srgb,var(--primary) 7%,var(--surface));border:1px solid color-mix(in srgb,var(--primary) 18%,var(--line));font-size:12px;color:var(--dim)!important;line-height:1.5}
        .permission-note strong{color:var(--ink)!important}
        @media(min-width:901px){[data-testid="stSidebar"]{width:310px!important;min-width:310px!important;max-width:310px!important}[data-testid="stSidebar"]>div:first-child{width:310px!important}}
        @media(min-width:701px){.st-key-dispatch-layout [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important}.st-key-dispatch-layout [data-testid="stColumn"]{min-width:0!important}.st-key-dispatch-layout [data-testid="stColumn"]:first-child{flex:0 0 260px!important}.st-key-dispatch-layout [data-testid="stColumn"]:last-child{flex:1 1 0!important}}
        @media(min-width:1200px){.st-key-dispatch-layout [data-testid="stColumn"]:first-child{flex-basis:300px!important}}
        @media(max-width:700px){.dispatch-fields{grid-template-columns:110px 1fr}.block-container{padding:4.4rem .85rem 3rem}.dispatch-top{gap:10px}.customer-hero{text-align:left}.customer-hero h1{font-size:31px}.service-chips{justify-content:flex-start}div[data-testid="stForm"]{padding:22px 17px;border-radius:19px}
        .st-key-dispatch-queue{height:150px!important;overflow-x:auto!important}
        .st-key-dispatch-queue [data-testid="stVerticalBlock"]{display:grid;grid-auto-flow:column;grid-template-rows:70px 40px;grid-auto-columns:240px;gap:8px}}
        @media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
        </style>''', unsafe_allow_html=True)
