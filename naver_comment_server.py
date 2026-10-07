"""블로그 댓글 도우미 (인터넷에 올려서 폰으로 쓰는 서버 버전)

환경변수:  ANTHROPIC_API_KEY (필수), APP_PASSWORD (필수, 아무나 못 쓰게 하는 비밀번호), PORT (자동)
실행:      python naver_comment_server.py

블로그 링크/아이디를 넣으면 최신글을 읽고 20대 여성 블로거 말투 댓글 초안을 만들어줘요.
공감 누르기와 댓글 등록은 직접 해주세요 (자동 등록은 네이버에서 제재될 수 있어요).
"""
import json
import os
import re
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer

import anthropic
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}

PROMPT = """너는 블로그를 즐겨 보는 20대 여성 이웃이야. 아래 블로그 글을 읽고 댓글 3개를 써줘.
종류: 공감형 / 질문형(글쓴이에게 자연스럽게 궁금한 점 묻기) / 한마디형(내 경험·한마디 덧붙이기)

말투 규칙:
- 실제 20대 여성이 네이버 블로그에 다는 댓글처럼 '~했어요', '~네요', '~더라구요', '~ㅎㅎ', '~ㅠㅠ'를 자연스럽게 섞기
- 각 댓글 1~3문장, 글에 나온 구체적인 내용(장소·음식·감정·팁 등)을 꼭 하나 이상 언급
- 이모티콘/이모지는 댓글당 최대 1개, 느낌표 남발 금지
- '좋은 글 감사합니다' 같은 뻔한 문장, 과한 칭찬, 광고·홍보·맞구독 요청 금지
- 글에 없는 사실을 지어내지 말 것, 세 댓글의 어투를 서로 다르게

JSON만 출력: {"comments":[{"type":"공감형","text":"..."},{"type":"질문형","text":"..."},{"type":"한마디형","text":"..."}]}
"""


# ---------- 네이버 읽기 + 댓글 생성 ----------
def extract_blog_id(s: str) -> str:
    m = re.search(r"blog\.naver\.com/([^/?#]+)", s)
    return m.group(1) if m else s.strip()


def post_from_target(target: str):
    """링크(글 주소)면 그 글, 아이디/블로그 주소면 최신글. (blog_id, title, link) 반환"""
    m = re.search(r"blog\.naver\.com/([^/?#]+)/(\d+)", target)
    if m:  # 특정 글 링크
        return m.group(1), None, f"https://blog.naver.com/{m.group(1)}/{m.group(2)}"
    bid = extract_blog_id(target)
    res = requests.get(f"https://rss.blog.naver.com/{bid}.xml", headers=HEADERS, timeout=10)
    res.raise_for_status()
    item = ET.fromstring(res.content).find("./channel/item")
    if item is None:
        raise RuntimeError("공개된 글이 없어요")
    return bid, item.findtext("title", "").strip(), item.findtext("link", "").split("?")[0]


def read_post(url: str):
    m = re.search(r"blog\.naver\.com/([^/?]+)/(\d+)", url)
    murl = f"https://m.blog.naver.com/{m.group(1)}/{m.group(2)}" if m else url
    res = requests.get(murl, headers=HEADERS, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    body = soup.select_one(".se-main-container, #postViewArea, .post_ct")
    if body is None:
        raise RuntimeError("본문을 못 찾았어요 (비공개 글이거나 구조가 달라요)")
    t = soup.select_one(".se-title-text, .tit_h3")
    text = re.sub(r"\n{3,}", "\n\n", body.get_text("\n", strip=True))[:6000]
    return (t.get_text(strip=True) if t else ""), text


def make_comments(api_key: str, title: str, text: str):
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-5-5", max_tokens=900,
        messages=[{"role": "user", "content": f"{PROMPT}\n제목: {title}\n\n본문:\n{text}"}],
    )
    raw = msg.content[0].text
    return json.loads(re.search(r"\{.*\}", raw, re.S).group(0))["comments"]


def handle(target: str) -> dict:
    try:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("서버에 ANTHROPIC_API_KEY가 설정되지 않았어요")
        bid, title, link = post_from_target(target)
        page_title, text = read_post(link)
        title = title or page_title
        return {"ok": True, "blog_id": bid, "title": title, "link": link,
                "comments": make_comments(key, title, text)}
    except Exception as e:
        return {"ok": False, "target": target, "error": str(e)}


# ---------- 웹 화면 ----------
PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>블로그 댓글 도우미</title>
<style>
:root{--bg:#fff7fa;--card:#fff;--ink:#3a2a31;--sub:#8d7580;--line:#f3d9e3;--pink:#ff8fb1;--pink-d:#ee6f98;--soft:#ffe8f0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif;line-height:1.55}
main{max-width:600px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:4px 0}
.lead{color:var(--sub);font-size:14px;margin:0 0 18px}
.card{background:var(--card);border:1.5px solid var(--line);border-radius:18px;padding:16px;margin-bottom:14px}
label{display:block;font-size:13px;font-weight:700;margin-bottom:6px}
input,textarea{width:100%;border:1.5px solid var(--line);background:var(--bg);color:var(--ink);border-radius:12px;padding:11px 12px;font:inherit;font-size:16px;outline:none}
input:focus,textarea:focus{border-color:var(--pink)}
textarea{min-height:110px;resize:vertical}
.hint{font-size:12px;color:var(--sub);margin:6px 0 0}
button{font:inherit;cursor:pointer;border:0;border-radius:12px}
#go{width:100%;background:var(--pink);color:#fff;font-weight:700;padding:14px;font-size:16px}
#go:disabled{opacity:.55;cursor:default}
.post{background:var(--card);border:1.5px solid var(--line);border-radius:16px;padding:14px;margin-bottom:12px}
.post h3{font-size:15px;margin:0 0 2px}
.post a{font-size:12px;color:var(--pink-d)}
.c{margin-top:12px}
.tag{display:inline-block;font-size:12px;font-weight:700;color:var(--pink-d);background:var(--soft);padding:2px 9px;border-radius:999px;margin-bottom:6px}
.c p{margin:0 0 8px;font-size:15px;white-space:pre-wrap;word-break:keep-all}
.b1{background:var(--pink);color:#fff;padding:9px 14px;font-size:13px;font-weight:700;margin-right:6px}
.b2{background:var(--soft);color:var(--ink);padding:9px 14px;font-size:13px}
.err{color:#d6456b;font-size:14px;margin:0 0 10px}
.status{color:var(--sub);font-size:13px;margin:10px 0}
.note{font-size:12px;color:var(--sub);text-align:center;margin-top:18px}
</style></head><body><main>
<h1>🌸 블로그 댓글 도우미</h1>
<p class="lead">링크나 아이디만 넣으면 최신글을 읽고, 20대 여성 블로거 말투로 댓글 초안을 만들어줘요.</p>

<div class="card">
  <label for="key">비밀번호</label>
  <input id="key" type="password" placeholder="내가 정한 비밀번호" autocomplete="off">
  <p class="hint">이 폰의 브라우저에만 저장돼요.</p>
</div>

<div class="card">
  <label for="targets">블로그 링크 또는 아이디 (한 줄에 하나씩)</label>
  <textarea id="targets" placeholder="https://blog.naver.com/아이디&#10;아이디2&#10;https://blog.naver.com/아이디3/123456789"></textarea>
  <p class="hint">블로그 주소/아이디는 최신글, 글 주소는 그 글에 맞춰 써요.</p>
</div>

<button id="go">댓글 만들기 ✨</button>
<div class="status" id="status"></div>
<div id="out"></div>
<p class="note">공감 누르기와 댓글 등록은 직접 해주세요. 자동 등록은 네이버에서 제재될 수 있어요.</p>
</main>
<script>
var $=function(i){return document.getElementById(i)};
try{$("key").value=localStorage.getItem("bch_key")||""}catch(e){}

function card(r){
  var box=document.createElement("div"); box.className="post";
  if(!r.ok){
    var e=document.createElement("p"); e.className="err"; e.textContent="⚠️ "+r.target+" — "+r.error;
    box.appendChild(e); return box;
  }
  var h=document.createElement("h3"); h.textContent=r.blog_id+" · "+r.title;
  var a=document.createElement("a"); a.href=r.link; a.target="_blank"; a.rel="noopener"; a.textContent="글 열기";
  box.appendChild(h); box.appendChild(a);
  r.comments.forEach(function(c){
    var d=document.createElement("div"); d.className="c";
    var t=document.createElement("span"); t.className="tag"; t.textContent=c.type;
    var p=document.createElement("p"); p.textContent=c.text;
    var b1=document.createElement("button"); b1.className="b1"; b1.textContent="복사하고 글 열기 ✨";
    var b2=document.createElement("button"); b2.className="b2"; b2.textContent="복사만";
    function copy(btn,label,open){
      navigator.clipboard.writeText(c.text).then(function(){
        if(open) window.open(r.link,"_blank","noopener");
        btn.textContent=open?"복사 완료! 붙여넣기만 하세요 ✓":"복사됐어요 ✓";
        setTimeout(function(){btn.textContent=label},2200);
      });
    }
    b1.onclick=function(){copy(b1,"복사하고 글 열기 ✨",true)};
    b2.onclick=function(){copy(b2,"복사만",false)};
    d.appendChild(t); d.appendChild(p); d.appendChild(b1); d.appendChild(b2);
    box.appendChild(d);
  });
  return box;
}

$("go").onclick=async function(){
  var key=$("key").value.trim();
  var lines=$("targets").value.split("\\n").map(function(s){return s.trim()}).filter(Boolean);
  if(!key||!lines.length){$("status").textContent="비밀번호와 블로그 링크를 입력해 주세요";return}
  try{localStorage.setItem("bch_key",key)}catch(e){}
  $("go").disabled=true; $("out").innerHTML="";
  for(var i=0;i<lines.length;i++){
    $("status").textContent="("+(i+1)+"/"+lines.length+") 글 읽고 댓글 쓰는 중... 🌷";
    try{
      var res=await fetch("/api",{method:"POST",body:JSON.stringify({pw:key,target:lines[i]})});
      $("out").appendChild(card(await res.json()));
    }catch(e){
      $("out").appendChild(card({ok:false,target:lines[i],error:"서버 연결 실패"}));
    }
  }
  $("status").textContent="끝! 마음에 드는 댓글을 골라 붙여넣어 주세요 🌷";
  $("go").disabled=false;
};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}")
        pw = os.environ.get("APP_PASSWORD", "")
        if not pw or data.get("pw", "") != pw:
            result = {"ok": False, "target": data.get("target", ""), "error": "비밀번호가 맞지 않아요"}
        else:
            result = handle(data.get("target", ""))
        out = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"서버 시작: 포트 {port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
