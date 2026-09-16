# -*- coding: utf-8 -*-
"""生成"教材原文阅读器"（单文件 HTML，双击即可离线打开）。

输出：data/reader.html
  - 左栏：章节树（章 / 节 / 小节），点一下看该节**原文**
  - 右栏：原文，**图题处内嵌插图**（点击放大）
  - 顶部：检索框 —— 与 engine.retrieval 同一套逻辑
    （标题索引入口 → 段落级 BM25 → AND 降级 OR → 两条拒答判据：
     ①所有实词 DF=0；②≥2 个实词但每个命中词 DF≤2），
    用 JS 复刻；分词与 BM25 的语料由 Python 预计算后内嵌，
    因此**网页里的排序与后端一致**，不是另做一套。

为什么做成单文件离线 HTML：项目约定"零下载、依赖随项目走"，
阅读器不该要求学生装 Python 或起服务。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from engine.config import TEXTBOOKS_MD_DIR       # noqa: E402
from engine.retrieval import (                    # noqa: E402
    BM25, build_chunks, parse_markdown, tokenize,
)

BOOKS = [
    "计算机网络（第8版）_谢希仁_上半",
    "计算机网络（第8版）_谢希仁_下半",
]
SECTION_MAX_LEVEL = 3          # 章/节/小节 作为"章节入口"


# ------------------------------------------------------------------ 解析

def _load_items(book: str) -> list[dict]:
    md = TEXTBOOKS_MD_DIR / f"{book}.md"
    if not md.exists():
        return []
    return parse_markdown(md.read_text(encoding="utf-8"))


def _build_sections(items: list[dict], book: str) -> tuple[list[dict], list[dict]]:
    """元素序列 → (章节列表, 每节的展示块列表)。

    只有 level ≤ 3 的标题开新节（与 retrieval.build_chunks 的"章节入口"一致）；
    更深层的标题作为节内的小标题展示。
    """
    sections: list[dict] = []
    cur: dict | None = None

    def ensure(path: str, page) -> dict:
        nonlocal cur
        if cur is None:
            cur = {"book": book, "lv": 1, "title": "（前言）", "path": path,
                   "page": page, "blocks": []}
            sections.append(cur)
        return cur

    for it in items:
        if it["kind"] == "heading" and it["level"] <= SECTION_MAX_LEVEL:
            cur = {"book": book, "lv": it["level"], "title": it["text"],
                   "path": it["path"], "page": it["page"], "blocks": []}
            sections.append(cur)
            continue
        sec = ensure(it["path"], it["page"])
        if it["kind"] == "heading":
            sec["blocks"].append({"k": "h", "lv": it["level"], "t": it["text"],
                                  "pg": it["page"]})
        elif it["kind"] == "figure":
            url = it["url"].replace("../", "")
            sec["blocks"].append({"k": "f", "u": url, "t": it["text"],
                                  "pg": it["page"]})
        elif it["kind"] == "table":
            sec["blocks"].append({"k": "tb", "t": it["text"], "pg": it["page"]})
        else:
            sec["blocks"].append({"k": "p", "t": it["text"], "pg": it["page"]})
    return sections, [s["blocks"] for s in sections]


def _section_of(path: str, by_path: dict[str, int]) -> int:
    """把块的 section_path 归到最长的已建节路径上。"""
    parts = path.split(" > ")
    for n in range(len(parts), 0, -1):
        key = " > ".join(parts[:n])
        if key in by_path:
            return by_path[key]
    return 0


# ------------------------------------------------------------------ 检索语料

def _build_search_data(sections: list[dict], items_by_book: dict[str, list[dict]]):
    """构造内嵌的检索语料：块 id 序列 + 词表 + 标题词。"""
    chunks: list[dict] = []
    for book, items in items_by_book.items():
        chunks.extend(build_chunks(
            items, doc_title=book, course="计算机网络", source_file=f"{book}.md"))

    # 按书分别建路径索引：上下两册是同一本教材的前后半本，
    # 万一出现同名章节路径，也不能让后一本覆盖前一本。
    by_book_path: dict[str, dict[str, int]] = {}
    for i, s in enumerate(sections):
        by_book_path.setdefault(s["book"], {})[s["path"]] = i

    vocab: dict[str, int] = {}
    out_chunks: list[dict] = []
    title_tokens: list[list[int]] = [[] for _ in sections]

    def tid(term: str) -> int:
        i = vocab.get(term)
        if i is None:
            i = len(vocab)
            vocab[term] = i
        return i

    for c in chunks:
        book = c.get("source_file", "")[:-3]
        si = _section_of(c["section_path"], by_book_path.get(book, {}))
        toks = [tid(t) for t in tokenize(c["text"])]
        if c.get("is_title"):
            if 0 <= si < len(title_tokens):
                title_tokens[si] = sorted(set(toks))
            continue                      # 标题块本身不作为"原文片段"返回
        out_chunks.append({
            "s": si,
            "p": c.get("page_no"),
            "tk": toks,
            "x": c["text"],
        })

    return {
        "chunks": out_chunks,
        "vocab": [t for t, _ in sorted(vocab.items(), key=lambda kv: kv[1])],
        "titleTokens": title_tokens,
    }


# ------------------------------------------------------------------ 渲染

_CSS = """
:root{--bg:#0f1115;--panel:#161a21;--panel2:#1d222b;--line:#2a313d;
      --fg:#e6eaf2;--dim:#93a0b4;--accent:#5a8dd6;--gold:#e0b266;}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
  font:15px/1.9 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:12px 20px;
  background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20}
header h1{font-size:16px;margin:0;font-weight:600;white-space:nowrap}
header h1 small{color:var(--dim);font-weight:400;margin-left:8px;font-size:12px}
#q{flex:1;max-width:560px;padding:9px 14px;border-radius:8px;border:1px solid var(--line);
  background:var(--panel2);color:var(--fg);font-size:14px;outline:none}
#q:focus{border-color:var(--accent)}
#go{padding:9px 18px;border:0;border-radius:8px;background:var(--accent);color:#fff;
  font-size:14px;cursor:pointer}
#go:hover{filter:brightness(1.12)}
#hint{color:var(--dim);font-size:12.5px}
#app{display:flex;height:calc(100% - 57px)}
aside{width:290px;min-width:290px;overflow:auto;background:var(--panel);
  border-right:1px solid var(--line);padding:10px 6px}
aside .book{margin:10px 8px 4px;color:var(--gold);font-weight:600;font-size:13px}
aside a{display:block;padding:5px 10px;border-radius:6px;color:var(--fg);
  text-decoration:none;font-size:13.5px;cursor:pointer;line-height:1.5}
aside a:hover{background:var(--panel2)}
aside a.on{background:var(--accent);color:#fff}
aside a.lv2{padding-left:24px;color:var(--dim)}
aside a.lv3{padding-left:40px;color:var(--dim);font-size:13px}
main{flex:1;overflow:auto;padding:28px 44px 120px;scroll-behavior:smooth}
h2.sec{font-size:22px;margin:6px 0 4px;padding-bottom:10px;border-bottom:2px solid var(--line)}
.crumb{color:var(--dim);font-size:12.5px;margin-bottom:18px}
main h4{font-size:16px;margin:26px 0 8px;color:#cfe0f5}
main h5{font-size:14.5px;margin:20px 0 6px;color:var(--dim)}
p.para{margin:0 0 15px;text-indent:2em;text-align:justify}
.pg{display:inline-block;min-width:34px;margin-right:8px;padding:0 6px;border-radius:4px;
  background:var(--panel2);color:var(--dim);font-size:11.5px;text-indent:0;
  vertical-align:1px;font-variant-numeric:tabular-nums}
figure{margin:20px 0 24px;text-align:center}
figure img{max-width:min(760px,100%);border:1px solid var(--line);border-radius:8px;
  background:#fff;cursor:zoom-in;transition:transform .15s}
figure img:hover{transform:translateY(-2px)}
figcaption{color:var(--dim);font-size:12.5px;margin-top:8px}
table.tbl{width:100%;border-collapse:collapse;margin:16px 0 22px;font-size:13.5px}
table.tbl th,table.tbl td{border:1px solid var(--line);padding:7px 10px;text-align:left;
  vertical-align:top}
table.tbl th{background:var(--panel2);color:#cfe0f5;font-weight:600}
table.tbl tr:hover td{background:rgba(90,141,214,.07)}
mark{background:#5a8dd6;color:#fff;border-radius:3px;padding:0 2px}
.card{border:1px solid var(--line);background:var(--panel);border-radius:10px;
  padding:12px 16px;margin-bottom:12px;cursor:pointer}
.card:hover{border-color:var(--accent)}
.card .t{color:#cfe0f5;font-weight:600;font-size:14px}
.card .m{color:var(--dim);font-size:12px;margin:4px 0 6px}
.card .x{color:var(--fg);font-size:13.5px;opacity:.9}
.card .sc{float:right;color:var(--gold);font-size:12px}
.empty{color:var(--dim);padding:40px 0;text-align:center}
#lb{position:fixed;inset:0;background:rgba(0,0,0,.9);display:none;z-index:50;
  align-items:center;justify-content:center;cursor:zoom-out}
#lb img{max-width:96%;max-height:96%;background:#fff;border-radius:6px}
"""

_JS = r"""
const S = DATA.sections, C = DATA.chunks, V = DATA.vocab, TT = DATA.titleTokens;
const ID2 = new Map(); V.forEach((w,i)=>ID2.set(w,i));
const MAXLEN = V.reduce((a,w)=>Math.max(a,w.length),1);

/* ---- 查询分词：对语料词表做正向最大匹配 ----
   后端用 jieba+词性过滤；网页里没有 jieba，改用"语料词表 + 正向最大匹配"，
   词表本身来自后端同一套分词结果，因此"物理层"这类专业词一定在表里。
   与后端一致的两条约定：单汉字丢弃（信息量低）、单字符英文/数字保留。

   额外返回 unknown（未收录的连续中文串）：**这一条不能省**。
   否则"量子纠缠"会因为没有词命中而被拆成单字全部丢掉，前端只能说
   "未能提取关键词"——而用户要的是"整本书里没有这个词，如实说没有"。 */
const FUNC_CHARS=new Set('的了是在和就都而及与着或之也这那什么怎怎样如何为哪些'+
                         '没有是否多少介绍讲解一下意思请问知道告诉');
function isFuncRun(r){for(const ch of r) if(!FUNC_CHARS.has(ch)) return false; return true;}
function seg(q){
  const s=(q||'').toLowerCase().replace(/[\s，。！？；：、,\.!\?;:]+/g,' ').trim();
  const toks=[], unknown=[];
  for(const p of s.split(' ').filter(Boolean)){
    let i=0, run='';
    const closeRun=()=>{if(run.length>=2) unknown.push(run); run='';};
    while(i<p.length){
      let hit=null;
      for(let L=Math.min(MAXLEN,p.length-i);L>=2;L--){
        const w=p.substr(i,L); if(ID2.has(w)){hit=w;break;}
      }
      if(hit){ closeRun(); toks.push(hit); i+=hit.length; }
      else{
        const ch=p[i];
        if(/[\u4e00-\u9fff]/.test(ch)) run+=ch;
        else { closeRun(); toks.push(ch); }
        i+=1;
      }
    }
    closeRun();
  }
  return {toks, unknown};
}

/* ---- BM25（k1=1.5, b=0.75，与后端逐项一致） ---- */
const K1=1.5, B=0.75, N=C.length;
const dl=C.map(c=>c.tk.length);
let AVG=0; for(const n of dl) AVG+=n; AVG=AVG/Math.max(N,1);
const df=new Map(), post=new Map();
{
  for(let i=0;i<N;i++){
    const tf=new Map();
    for(const t of C[i].tk) tf.set(t,(tf.get(t)||0)+1);
    for(const [t,f] of tf){
      df.set(t,(df.get(t)||0)+1);
      let ps=post.get(t); if(!ps){ps=[];post.set(t,ps);}
      ps.push([i,f]);
    }
  }
}
function idf(t){const d=df.get(t)||0;return Math.log((N-d+0.5)/(d+0.5)+1);}
function bm25(ids){
  const sc=new Float64Array(N);
  for(const t of new Set(ids)){
    const I=idf(t), ps=post.get(t); if(!ps) continue;
    for(const [i,f] of ps){
      const d=dl[i]||1;
      sc[i]+=I*f*(K1+1)/(f+K1*(1-B+B*d/(AVG||1)));
    }
  }
  return sc;
}

/* ---- 检索主流程：标题入口 → 段落 BM25（AND 降级 OR）→ DF=0 拒答 ---- */
function runSearch(query){
  const sg=seg(query);
  const toks=[...new Set(sg.toks)];
  const unknown=[...new Set(sg.unknown)];
  if(!toks.length){
    // 一个词都没切出来：若里面还有"像专业术语的连续中文串"→ 如实说没有；
    // 若整句都是"什么是/怎么/介绍一下"这类虚词 → 提示问得再具体些。
    const real=unknown.filter(r=>!isFuncRun(r));
    if(real.length) return {status:'not_found',missing:real,known:[]};
    return {status:'empty'};
  }
  const ids=toks.map(t=>ID2.get(t)).filter(v=>v!==undefined);
  const knownIds=ids.filter(t=>(df.get(t)||0)>0);
  const known=toks.filter(t=>knownIds.includes(ID2.get(t)));
  const missing=toks.filter(t=>!known.includes(t)).concat(unknown);
  if(!knownIds.length) return {status:'not_found',missing:toks.concat(unknown),known:[]};
  /* 拒答判据二（与 engine.retrieval 一致）：≥2 个实词，而**每一个命中词**全库都只
     出现 ≤2 次 —— 说明书只在别处顺带提过字面，并没有真正展开讲这个知识点。
     实测「量子纠缠」：全库只有第 7 章"量子密码"顺带 1 次"量子"、"纠缠"1 次，
     照常返回会让用户以为书里讲过量子纠缠。少了这条，网页与后端结论就不一致。 */
  if(toks.length>=2 && knownIds.every(t=>(df.get(t)||0)<=2))
    return {status:'not_found',missing:toks,known:[]};

  const qset=new Set(knownIds);
  const hits=[];
  TT.forEach((tk,si)=>{
    if(!tk.length) return;
    const h=tk.filter(t=>qset.has(t));
    if(!h.length) return;
    const score=h.reduce((a,t)=>a+idf(t),0)*h.length/Math.max(tk.length,1);
    hits.push({si,n:h.length,lv:S[si].lv,score:+score.toFixed(3)});
  });
  hits.sort((a,b)=>b.n-a.n||a.lv-b.lv||b.score-a.score);

  function rank(requireAll){
    const sc=bm25(knownIds); const rows=[];
    for(let i=0;i<N;i++){
      if(sc[i]<=1e-9) continue;
      if(requireAll){
        const set=new Set(C[i].tk);
        if(!knownIds.every(t=>set.has(t))) continue;
      }
      rows.push({i,score:+sc[i].toFixed(3)});
    }
    rows.sort((a,b)=>b.score-a.score);
    return rows.slice(0,10);
  }
  let rows=rank(true);
  if(!rows.length) rows=rank(false);
  if(!hits.length && !rows.length) return {status:'not_found',missing:toks,known:[]};
  return {status:'ok',known,missing,hits:hits.slice(0,6),rows};
}

/* ---- 界面 ---- */
const nav=document.getElementById('nav'), content=document.getElementById('content');
const hint=document.getElementById('hint');
let marks=new Set();

function esc(t){return (t||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

/* Markdown 管道表格 → 真表格。
   教材里的对照表（同轴电缆/双绞线类别、SONET 速率、CIDR 掩码）拍平成一行文字
   基本没法读，必须按表格渲染；表头行用 <th>。 */
function tableHtml(md){
  const rows=[];
  for(const line of (md||'').split('\n')){
    const t=line.trim();
    if(t[0]!=='|') continue;
    const cells=t.replace(/^\||\|$/g,'').split('|').map(c=>c.trim().replace(/\\\|/g,'|'));
    if(cells.length&&cells.every(c=>/^[-:\s]*$/.test(c))) continue;
    rows.push(cells);
  }
  if(!rows.length) return '';
  let h='<table class="tbl">';
  rows.forEach((r,i)=>{
    h+='<tr>'+r.map(c=>i===0?`<th>${esc(c)}</th>`:`<td>${esc(c)}</td>`).join('')+'</tr>';
  });
  return h+'</table>';
}
function hl(text){
  const keys=[...marks].filter(k=>k.length>1).sort((a,b)=>b.length-a.length);
  if(!keys.length) return esc(text);
  let out=esc(text);
  for(const k of keys){
    out=out.replace(new RegExp(k.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'gi'),
                    m=>'\u0001'+m+'\u0002');
  }
  return out.replace(/\u0001/g,'<mark>').replace(/\u0002/g,'</mark>');
}
const bookName=b=>DATA.bookLabels[b]||b;

function buildNav(){
  let last=null;
  S.forEach((s,i)=>{
    if(s.book!==last){
      last=s.book;
      const d=document.createElement('div');
      d.className='book'; d.textContent=bookName(s.book);
      nav.appendChild(d);
    }
    const a=document.createElement('a');
    a.className='lv'+Math.min(s.lv,3);
    a.textContent=s.title; a.dataset.si=i;
    a.onclick=()=>show(i);
    nav.appendChild(a);
  });
}
function show(si){
  marks=new Set(); hint.textContent='';
  nav.querySelectorAll('a').forEach(a=>a.classList.toggle('on',+a.dataset.si===si));
  const s=S[si], h=[];
  h.push(`<div class="crumb">${esc(bookName(s.book))} · 第 ${s.page??'?'} 页</div>`);
  h.push(`<h2 class="sec">${esc(s.title)}</h2>`);
  for(const b of s.blocks){
    const pg=b.pg?`<span class="pg">P${b.pg}</span>`:'';
    if(b.k==='h'){const tag=b.lv<=4?'h4':'h5';h.push(`<${tag}>${esc(b.t)}</${tag}>`);}
    else if(b.k==='f') h.push(`<figure><img src="${esc(b.u)}" alt="${esc(b.t)}" loading="lazy">`+
      `<figcaption>${esc(b.t)} ${pg}</figcaption></figure>`);
    else if(b.k==='tb') h.push(tableHtml(b.t));
    else h.push(`<p class="para">${pg}${hl(b.t)}</p>`);
  }
  content.innerHTML=h.join('');
  content.scrollTop=0;
  bindZoom();
}
function bindZoom(){
  content.querySelectorAll('figure img').forEach(im=>{
    im.onclick=()=>{document.getElementById('lbimg').src=im.src;
      document.getElementById('lb').style.display='flex';};
  });
}
document.getElementById('lb').onclick=()=>document.getElementById('lb').style.display='none';
document.addEventListener('keydown',e=>{if(e.key==='Escape')
  document.getElementById('lb').style.display='none';});
document.getElementById('go').onclick=doSearch;
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')doSearch();});

function showHome(){
  marks=new Set(); hint.textContent='';
  nav.querySelectorAll('a').forEach(a=>a.classList.remove('on'));
  content.innerHTML=
    `<h2 class="sec">${esc(DATA.title)}</h2>`+
    `<div class="crumb">${DATA.stats.pages} 页 · ${DATA.stats.chunks} 个原文片段 · `+
    `${DATA.stats.figures} 张插图 · ${DATA.stats.tables} 张表格 · ${DATA.stats.sections} 个章节入口</div>`+
    `<p class="para">左栏点章节看该节<b>原文</b>：插图内嵌在它原来的位置（点击放大），`+
    `表格按表格显示 —— 块的顺序就是原书的顺序，没有做任何重排。`+
    `顶部输入框按知识点检索：先命中标题，标题不中再给原文段落；`+
    `整本书都没有的词会直接说明"未找到"，不做猜测性作答。</p>`;
}

function doSearch(){
  const q=document.getElementById('q').value.trim();
  if(!q){showHome();return;}
  const r=runSearch(q);
  content.scrollTop=0;
  if(r.status==='empty'){hint.textContent='未能提取出有效关键词，请再具体一些。';return;}
  if(r.status==='not_found'){
    marks=new Set();
    hint.textContent=`书中未找到「${r.missing.join('、')}」`;
    content.innerHTML=`<h2 class="sec">未找到</h2><p class="para">整本书里没有出现`+
      `「${esc(r.missing.join('、'))}」，不做猜测性作答。</p>`;
    return;
  }
  marks=new Set(r.known);
  hint.textContent=(r.missing.length?`「${r.missing.join('、')}」未出现，按其余关键词检索 · `:'')
    +`标题命中 ${r.hits.length} · 原文片段 ${r.rows.length}`;
  const out=[`<h2 class="sec">检索：${esc(q)}</h2>`,
             `<div class="crumb">关键词：${esc(r.known.join('、'))}</div>`];
  if(r.hits.length){
    out.push('<h4>命中的章节</h4>');
    for(const t of r.hits){
      const s=S[t.si];
      out.push(`<div class="card" data-si="${t.si}"><span class="sc">命中 ${t.n} 词</span>`+
        `<div class="t">${esc(s.title)}</div><div class="m">${esc(bookName(s.book))} · `+
        `第 ${s.page??'?'} 页</div></div>`);
    }
  }
  if(r.rows.length){
    out.push('<h4>原文片段</h4>');
    for(const x of r.rows){
      const c=C[x.i], s=S[c.s];
      out.push(`<div class="card" data-si="${c.s}"><span class="sc">${x.score}</span>`+
        `<div class="t">${esc(s?s.title:'')}</div><div class="m">第 ${c.p??'?'} 页</div>`+
        `<div class="x">${hl(c.x.slice(0,160))}${c.x.length>160?'…':''}</div></div>`);
    }
  }
  content.innerHTML=out.join('');
  content.querySelectorAll('.card').forEach(el=>{el.onclick=()=>show(+el.dataset.si);});
}

buildNav(); showHome();
"""


def _render_html(sections: list[dict], search: dict, stats: dict) -> str:
    payload = {
        "title": "计算机网络（第8版）· 教材原文阅读器",
        "bookLabels": {"计算机网络（第8版）_谢希仁_上半": "计算机网络 第8版 · 上册",
                       "计算机网络（第8版）_谢希仁_下半": "计算机网络 第8版 · 下册"},
        "sections": sections,
        "chunks": search["chunks"],
        "vocab": search["vocab"],
        "titleTokens": search["titleTokens"],
        "stats": stats,
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")          # 防止正文里出现 </script> 截断脚本
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<title>计算机网络（第8版）· 教材原文阅读器</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        "<header><h1>计算机网络 第8版 <small>教材原文阅读器</small></h1>\n"
        "<input id=\"q\" placeholder=\"输入知识点，如：物理层 / 什么是物理层 / CSMA/CD\">\n"
        "<button id=\"go\">检索</button><span id=\"hint\"></span></header>\n"
        "<div id=\"app\"><aside id=\"nav\"></aside><main id=\"content\"></main></div>\n"
        "<div id=\"lb\"><img id=\"lbimg\" alt=\"\"></div>\n"
        f"<script>const DATA={blob};\n{_JS}</script>\n</body>\n</html>\n"
    )


# ------------------------------------------------------------------ 主流程

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="输出 HTML（默认 data/reader.html）")
    args = ap.parse_args()

    all_sections: list[dict] = []
    items_by_book: dict[str, list[dict]] = {}
    for book in BOOKS:
        items = _load_items(book)
        if not items:
            print(f"  [跳过] 未找到合并后的 Markdown：{book}.md")
            continue
        items_by_book[book] = items
        secs, blocks = _build_sections(items, book)
        for s, bl in zip(secs, blocks):
            s["blocks"] = bl
        all_sections.extend(secs)
        print(f"  {book}: {len(secs)} 节 / "
              f"{sum(len(s['blocks']) for s in secs)} 块")

    if not all_sections:
        print("没有任何可用的教材 Markdown，先跑 OCR 与合并。")
        return 1

    for i, s in enumerate(all_sections):
        s["id"] = i
    search = _build_search_data(all_sections, items_by_book)

    n_fig = sum(1 for s in all_sections for b in s["blocks"] if b["k"] == "f")
    n_tbl = sum(1 for s in all_sections for b in s["blocks"] if b["k"] == "tb")
    pages = [b["pg"] for s in all_sections for b in s["blocks"] if b["pg"]]
    stats = {
        "sections": len(all_sections),
        "chunks": len(search["chunks"]),
        "figures": n_fig,
        "tables": n_tbl,
        "vocab": len(search["vocab"]),
        "pages": f"{min(pages)}–{max(pages)}" if pages else "-",
    }

    out = Path(args.out) if args.out else (TEXTBOOKS_MD_DIR.parent / "reader.html")
    out.write_text(_render_html(all_sections, search, stats), encoding="utf-8")
    mb = out.stat().st_size / 1048576
    print(f"完成：{out}")
    print(f"  {stats['sections']} 节 / {stats['chunks']} 原文片段 / "
          f"{stats['figures']} 张插图 / 词表 {stats['vocab']} / 页码 {stats['pages']}")
    print(f"  文件 {mb:.1f} MB（单文件离线，插图按相对路径引用 data/figures/）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
