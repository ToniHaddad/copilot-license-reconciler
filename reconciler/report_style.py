"""Styles and the theme toggle for the report."""
CSS = """
:root{--bg:#f4f1ea;--surf:#fffdf8;--ink:#1d2623;--muted:#5b6662;--line:#ddd6c8;--accent:#0d6b61;--accent-soft:#d9ece8;
--warn:#a8480e;--warn-soft:#f6e2d3;--ok:#1d7a4a;--bad:#b3261e;
--c-zah:#6a4c9c;--c-jbe:#2a5db0;--c-sai:#c4521a;--c-tri:#14796d;--c-hq:#8a7414;
--c-active:#2f8f5b;--c-confirmed_inactive:#c4521a;--c-unknown:#9a9a9a;--c-unassigned:#d9a521;
--bar-all:#7a8a86;--bar-since:#0d6b61;--buy:#b3592e;--realloc:#0d6b61;--shadow:0 1px 2px rgba(30,40,35,.08)}
:root[data-theme=dark]{--bg:#111715;--surf:#18201d;--ink:#e8eeeb;--muted:#9bada6;--line:#2b3733;--accent:#52c4b3;--accent-soft:#1c3a35;
--warn:#f0a070;--warn-soft:#3a2819;--ok:#5fcf91;--bad:#ff8a80;
--c-zah:#b79cf0;--c-jbe:#7fa9ef;--c-sai:#f08a52;--c-tri:#4ccbb9;--c-hq:#d9c24f;
--c-active:#4cc486;--c-confirmed_inactive:#f08a52;--c-unknown:#8a8f8d;--c-unassigned:#e6bd4a;
--bar-all:#6f817c;--bar-since:#52c4b3;--buy:#e08a5a;--realloc:#52c4b3;--shadow:none}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111715;--surf:#18201d;--ink:#e8eeeb;--muted:#9bada6;--line:#2b3733;--accent:#52c4b3;--accent-soft:#1c3a35;
--warn:#f0a070;--warn-soft:#3a2819;--ok:#5fcf91;--bad:#ff8a80;
--c-zah:#b79cf0;--c-jbe:#7fa9ef;--c-sai:#f08a52;--c-tri:#4ccbb9;--c-hq:#d9c24f;
--c-active:#4cc486;--c-confirmed_inactive:#f08a52;--c-unknown:#8a8f8d;--c-unassigned:#e6bd4a;
--bar-all:#6f817c;--bar-since:#52c4b3;--buy:#e08a5a;--realloc:#52c4b3;--shadow:none}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:0 16px 56px}
header.top{padding:28px 0 8px;display:flex;gap:16px;justify-content:space-between;align-items:flex-start}
h1{font:700 clamp(1.5rem,4.5vw,2.2rem)/1.15 Georgia,"Times New Roman",serif;margin:0 0 6px;letter-spacing:-.01em}
.lede{color:var(--muted);margin:0;max-width:60ch}
h2{font:700 1.35rem/1.25 Georgia,"Times New Roman",serif;margin:44px 0 6px}
h3{margin:0;font-size:1.05rem}
h4{margin:18px 0 6px;font-size:.95rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.kicker{color:var(--accent);font-weight:700;font-size:.78rem;letter-spacing:.08em;text-transform:uppercase}
.muted{color:var(--muted)}
button.theme{background:var(--surf);color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:6px 12px;font:inherit;font-size:.85rem;cursor:pointer}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0 0}
.kpi{background:var(--surf);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:var(--shadow)}
.kpi b{display:block;font:700 1.55rem/1.1 Georgia,serif}
.kpi span{font-size:.82rem;color:var(--muted)}
.card{background:var(--surf);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0;box-shadow:var(--shadow)}
.rec h3{font-size:1.05rem;line-height:1.3}
.rec p{margin:.5em 0 .7em}
details{margin:6px 0}
summary{cursor:pointer;color:var(--accent);font-weight:600;font-size:.9rem}
details[open]>summary{margin-bottom:8px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
td:first-child{min-width:7.5rem}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.76rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:transparent;white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.src{font-family:Consolas,"SF Mono",monospace;font-size:.78rem;white-space:nowrap;color:var(--muted)}
td.ok{color:var(--ok);font-weight:700}td.bad{color:var(--bad);font-weight:700}
tr.total td{font-weight:700;border-top:2px solid var(--ink)}
code{font-family:Consolas,"SF Mono",monospace;font-size:.78rem;word-break:break-all}
.ev table{font-size:.8rem}
.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:.76rem}
.pill.warn{background:var(--warn-soft);color:var(--warn)}
.two{display:grid;grid-template-columns:1fr;gap:14px}
@media(min-width:820px){.two{grid-template-columns:1fr 1fr}}
.chart{width:100%;max-width:640px;height:auto;display:block;margin:0 auto}
td:last-child details{white-space:nowrap}
.recon td{white-space:nowrap}
.chart text{font-family:"Segoe UI",system-ui,sans-serif}
.tick{font-size:12px;fill:var(--muted)}
.note{font-size:11.5px;fill:var(--muted);font-style:italic}
.lbl{font-size:13px;font-weight:700;fill:var(--ink)}
.val{font-size:12.5px;font-weight:700;fill:var(--ink)}
.seglabel{font-size:12px;font-weight:700;fill:#fff}
.grid{stroke:var(--line);stroke-width:1}
.line{fill:none;stroke-width:2.2;stroke-linejoin:round}.line.thick{stroke-width:3.6}
.s-ZAH{stroke:var(--c-zah)}.s-JBE{stroke:var(--c-jbe)}.s-SAI{stroke:var(--c-sai)}.s-TRI{stroke:var(--c-tri)}.s-HQ{stroke:var(--c-hq)}
.f-ZAH{fill:var(--c-zah)}.f-JBE{fill:var(--c-jbe)}.f-SAI{fill:var(--c-sai)}.f-TRI{fill:var(--c-tri)}.f-HQ{fill:var(--c-hq)}
.l-ZAH{fill:var(--c-zah)}.l-JBE{fill:var(--c-jbe)}.l-SAI{fill:var(--c-sai)}.l-TRI{fill:var(--c-tri)}.l-HQ{fill:var(--c-hq)}
.xmark{fill:none;stroke-width:2.4;stroke-linecap:round}
.hollow{fill:var(--surf);stroke:var(--muted);stroke-width:1.6;stroke-dasharray:2 2}
.bar{fill:var(--bar-all)}.b-since{fill:var(--bar-since)}.b-buy{fill:var(--buy)}.b-realloc{fill:var(--realloc)}
.c-active{fill:var(--c-active)}.c-confirmed_inactive{fill:var(--c-confirmed_inactive)}.c-unknown{fill:var(--c-unknown)}.c-unassigned{fill:var(--c-unassigned)}
.seg{stroke:var(--surf);stroke-width:1}
.legend{font-size:.82rem;color:var(--muted);margin:4px 0 0}
.sw{display:inline-block;width:11px;height:11px;border-radius:2px;margin:0 4px -1px 10px}
.opts{display:grid;grid-template-columns:1fr;gap:14px;margin:14px 0}
@media(min-width:700px){.opts{grid-template-columns:1fr 1fr}}
.opt{background:var(--surf);border:1px solid var(--line);border-top:5px solid var(--buy);border-radius:12px;padding:16px 18px}
.opt.b{border-top-color:var(--realloc)}
.opt .sub{color:var(--muted);margin:2px 0 8px;font-size:.9rem}
.opt .big{font:700 2.1rem/1 Georgia,serif}
.opt .lab{margin:2px 0 10px;color:var(--muted);font-size:.85rem}
dl{display:grid;grid-template-columns:1fr auto;gap:4px 12px;margin:0;font-size:.9rem}dt{color:var(--muted)}dd{margin:0;text-align:right;font-weight:600;font-variant-numeric:tabular-nums}
.assume{font-size:.88rem;color:var(--muted);padding-left:18px}
.assume b{color:var(--ink)}
.callout{border-left:5px solid var(--c-sai);background:var(--warn-soft);border-radius:0 10px 10px 0;padding:12px 16px;margin:12px 0}
.fail li{margin:6px 0}
footer{margin-top:48px;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding-top:14px}
"""


JS = """
(function(){var b=document.getElementById('theme'),r=document.documentElement;
function cur(){var t=r.getAttribute('data-theme');if(t)return t;return matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}
b.addEventListener('click',function(){var n=cur()==='dark'?'light':'dark';r.setAttribute('data-theme',n);b.textContent=n==='dark'?'Light mode':'Dark mode'});
b.textContent=cur()==='dark'?'Light mode':'Dark mode';})();
"""


