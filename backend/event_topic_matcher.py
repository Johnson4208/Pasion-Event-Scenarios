"""Conservative topic recognition for public event-research articles.

Token-overlap alone accepted irrelevant R&D articles for GDP growth. This
matcher requires explicit economic concepts, supports common Vietnamese
phrases, and emits auditable match reasons. RSS snippets are not full text.
"""
import re
import unicodedata

VERSION="event-topics-v2"
ANCHORS={
 "GDP growth":("gdp","gross domestic product","economic growth","economic contraction",
    "economic output","economic recession","tang truong kinh te","tong san pham trong nuoc",
    "tang truong gdp","tang truong tong san pham","suy thoai kinh te","quy mo nen kinh te"),
 "Inflation":("inflation","consumer price index","cpi","price pressure","lam phat","chi so gia tieu dung"),
 "Labor market":("unemployment","payroll","employment","layoffs","job hiring","jobless","that nghiep","viec lam","thi truong lao dong"),
 "Oil supply":("oil supply","crude oil","opec","oil production","nguon cung dau","san luong dau","gia dau","supply disruption"),
 "Natural gas":("natural gas","lng","khí đốt","khi dot","gas supply"),
 "Energy prices":("energy prices","oil price","electricity prices","fuel prices","gia nang luong","gia dien","gia xang"),
 "Central bank policy":("interest rate","central bank","monetary policy","federal reserve","lai suat","ngan hang trung uong","chinh sach tien te"),
 "Credit conditions":("credit conditions","credit tightening","lending standards","dieu kien tin dung","tin dung"),
 "Bank lending":("bank lending","bank loan","cho vay ngan hang","du no tin dung"),
 "Conflict risk":("armed conflict","military conflict","war","ceasefire","escalation","xung dot","chien tranh","ngung ban"),
 "Sanctions":("sanctions","embargo","export restrictions","lenh trung phat","cam van"),
 "Trade disruption":("trade disruption","shipping disruption","supply chain disruption","port congestion","freight bottleneck","shipping delays","logistics disruption","gian doan chuoi cung ung","dut gay chuoi cung ung","un tac cang","dut gay thuong mai","gian doan van tai","cham giao hang","xuat nhap khau dinh tre"),
 "M&A activity":("mergers","acquisition","merger","mua ban sap nhap","m a deal"),
 "Earnings outlook":("earnings outlook","earnings guidance","profit forecast","du bao loi nhuan","trien vong loi nhuan"),
 "Hiring plans":("hiring","recruitment","headcount","tuyen dung","ke hoach nhan su"),
 "Consumer demand":("consumer demand","retail sales","consumption","suc mua","nhu cau tieu dung","ban le"),
 "Household spending":("household spending","consumer spending","household consumption","chi tieu ho gia dinh"),
 "Consumer confidence":("consumer confidence","consumer sentiment","niem tin tieu dung"),
 "Drug approvals":("fda approval","drug approval","new drug application","phe duyet thuoc"),
 "Healthcare costs":("healthcare costs","insurance premiums","medical costs","chi phi y te"),
 "Public health":("outbreak","public health","epidemic","dich benh","y te cong dong"),
 "Equity volatility":("stock volatility","market volatility","vix","bien dong chung khoan"),
 "Market liquidity":("market liquidity","funding stress","thanh khoan thi truong"),
 "Risk appetite":("risk appetite","risk on","risk off","khau vi rui ro"),
 "Fiscal policy":("fiscal policy","government budget","budget deficit","chinh sach tai khoa","ngan sach nha nuoc"),
 "Regulation":("regulation","regulatory rule","quy dinh","quan ly nha nuoc"),
 "Trade policy":("tariffs","trade agreement","trade policy","thue quan","chinh sach thuong mai"),
 "Property prices":("house prices","home prices","property prices","gia nha dat","gia bat dong san"),
 "Mortgage rates":("mortgage rate","mortgage lending","lai suat vay mua nha"),
 "Commercial demand":("commercial property","office leasing","commercial real estate","bat dong san thuong mai"),
 "Research funding":("research funding","science grants","tai tro nghien cuu","kinh phi nghien cuu"),
 "Clinical progress":("clinical trial","clinical study","thu nghiem lam sang"),
 "Technology adoption":("technology adoption","technology deployment","chuyen doi so","ung dung cong nghe"),
 "AI adoption":("artificial intelligence adoption","ai adoption","deployment of ai","ung dung ai","tri tue nhan tao"),
 "Semiconductor supply":("chip supply","semiconductor","chip shortage","ban dan","vi mach"),
 "Cybersecurity":("cybersecurity","cyber attack","data breach","an ninh mang","tan cong mang"),
}
STOP={"research","development","market","markets","world","global","asia","vietnam",
      "the","and","for","economic","growth","industry","business","risk","news","conditions"}

def normalize(s):
 s=unicodedata.normalize("NFKD",str(s or "").casefold()).replace("đ","d")
 s="".join(ch for ch in s if not unicodedata.combining(ch))
 return " ".join(re.findall(r"[a-z0-9]+",s))

def tokens(s):return set(normalize(s).split())

def _phrase(text,phrase):
 return bool(re.search(r"(?:^|\s)"+re.escape(normalize(phrase))+r"(?:\s|$)",text))

def inspect(title,description,factor,query_terms):
 content=normalize(str(title or "")+" "+str(description or ""))
 if not content:return {"eligible":False,"reason":"EMPTY_CONTENT","relevance":0,"matched":[]}
 anchors=ANCHORS.get(factor,())
 matched=[a for a in anchors if _phrase(content,a)]
 if matched:
  # A single explicit macroeconomic concept is enough; no reliance on the
  # number of arbitrary words in the research query.
  main=max(matched,key=len)
  relevance=min(1.0,.55+.1*min(4,len(tokens(main)))+.025*min(4,len(matched)))
  return {"eligible":True,"reason":"TOPIC_ANCHOR_MATCH","relevance":round(relevance,3),"matched":matched[:8]}
 # Fallback only for factors without a defined dictionary.
 if anchors:return {"eligible":False,"reason":"NO_TOPIC_ANCHOR","relevance":0,"matched":[]}
 qt=tokens(query_terms)-STOP
 common=qt&tokens(content)
 if len(common)<2:return {"eligible":False,"reason":"INSUFFICIENT_TOPIC_TERMS","relevance":0,"matched":[]}
 return {"eligible":True,"reason":"TOPIC_TOKEN_FALLBACK","relevance":round(len(common)/max(1,len(qt)),3),"matched":sorted(common)[:8]}
