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
    choice = st.sidebar.selectbox('Appearance', ['System', 'Dark', 'Light'], key='dispatch_appearance')
    dark = '--bg:#14181D;--surface:#1C222B;--surface2:#232B36;--ink:#EAEAE2;--dim:#9AA3AE;--amber:#F2A93B;--teal:#4FB8A6;--red:#E2542D;--line:#2E3742;'
    light = '--bg:#EDEFEA;--surface:#FFFFFF;--surface2:#F4F6F1;--ink:#1B2027;--dim:#56616D;--amber:#B36A16;--teal:#1F8F7D;--red:#B93A1A;--line:#D8DCD3;'
    variables = dark if choice == 'Dark' else light
    system = f'@media(prefers-color-scheme:dark){{:root{{{dark}}}}}' if choice == 'System' else ''
    st.markdown('<style>@import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono:wght@400&display=swap");'
        + ':root{' + variables + '}' + system + '''
        .stApp,[data-testid="stHeader"]{background:var(--bg);color:var(--ink)}
        .stApp{font-family:'IBM Plex Sans',sans-serif}
        h1,h2,h3,label,.dispatch-brand{font-family:'Space Grotesk',sans-serif;color:var(--ink)}
        [data-testid="stSidebar"]{background:var(--surface);border-right:1px solid var(--line)}
        [data-testid="stSidebar"] *{color:var(--ink)}
        .block-container{padding:2rem;max-width:1600px}
        .dispatch-top{display:flex;align-items:baseline;gap:24px;border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:20px;flex-wrap:wrap}
        .dispatch-brand{font-size:30px;font-weight:700}.dispatch-muted{color:var(--dim)}
        .dispatch-stage{font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:20px!important;display:flex;gap:12px;align-items:center;margin:24px 0 12px}
        .dispatch-stage>span{color:var(--dim);font-size:16px;border:1px solid var(--line);padding:3px 9px}
        .dispatch-request,.dispatch-stamp{background:var(--surface);border:1px solid var(--line);padding:20px;margin:12px 0;white-space:pre-wrap}
        .dispatch-request p,.dispatch-stamp p,.dispatch-explanation{max-width:64ch;line-height:1.65}
        .dispatch-stamp{border-left:5px solid var(--amber)}.dispatch-stamp strong{font-family:'Space Grotesk',sans-serif;font-size:23px;text-transform:uppercase;color:var(--amber)}
        .dispatch-stamp.resolved{border-color:var(--teal)}.dispatch-stamp.resolved strong{color:var(--teal)}
        .dispatch-stamp.conflict{border-color:var(--red)}.dispatch-stamp.conflict strong{color:var(--red)}
        .dispatch-fields{display:grid;grid-template-columns:150px 1fr;gap:10px 20px;background:var(--surface);border:1px solid var(--line);padding:20px}
        .dispatch-fields dt{color:var(--dim)}.dispatch-fields dd{margin:0;overflow-wrap:anywhere}
        .dispatch-table{width:100%;border-collapse:collapse;background:var(--surface);font-size:14px}
        .dispatch-table td,.dispatch-table th{text-align:left;padding:12px;border-bottom:1px solid var(--line);vertical-align:top}
        .dispatch-table th{color:var(--dim);font-weight:500}.dispatch-scroll{overflow-x:auto}
        .dispatch-pill{display:inline-block;border:1px solid currentColor;padding:3px 7px;font-size:12px;border-radius:3px;white-space:nowrap}
        .pending{color:var(--amber)}.resolved{color:var(--teal)}.conflict{color:var(--red)}
        .dispatch-log{background:var(--surface2);padding:16px;border-left:3px solid var(--line);font-family:'IBM Plex Mono',monospace;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}
        .dispatch-detail{animation:dispatch-enter .22s ease-out}@keyframes dispatch-enter{from{opacity:.5;transform:translateY(5px)}to{opacity:1;transform:none}}
        .stButton button,.stDownloadButton button{background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:3px;box-shadow:none;text-align:left}
        [data-baseweb="input"],[data-baseweb="input"] input,[data-baseweb="textarea"],textarea,[data-baseweb="select"]>div{background:var(--surface2)!important;color:var(--ink)!important;border-color:var(--line)!important}
        input::placeholder,textarea::placeholder{color:var(--dim)!important}
        .stButton button:focus-visible,.stDownloadButton button:focus-visible{outline:3px solid var(--amber);outline-offset:3px}
        [data-testid="stCaptionContainer"]{color:var(--dim)}
        [data-testid="stExpander"]{background:var(--surface);border-color:var(--line)}
        @media(min-width:701px){.st-key-dispatch-layout [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important}.st-key-dispatch-layout [data-testid="stColumn"]{min-width:0!important}.st-key-dispatch-layout [data-testid="stColumn"]:first-child{flex:0 0 260px!important}.st-key-dispatch-layout [data-testid="stColumn"]:last-child{flex:1 1 0!important}}
        @media(min-width:1200px){.st-key-dispatch-layout [data-testid="stColumn"]:first-child{flex-basis:300px!important}}
        @media(max-width:700px){.dispatch-fields{grid-template-columns:110px 1fr}.block-container{padding:1rem}.dispatch-top{gap:10px}
        .st-key-dispatch-queue{height:150px!important;overflow-x:auto!important}
        .st-key-dispatch-queue [data-testid="stVerticalBlock"]{display:grid;grid-auto-flow:column;grid-template-rows:70px 40px;grid-auto-columns:240px;gap:8px}}
        @media(prefers-reduced-motion:reduce){.dispatch-detail{animation:none}}
        </style>''', unsafe_allow_html=True)
