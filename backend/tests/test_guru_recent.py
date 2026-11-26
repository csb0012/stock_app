"""투자 대가 13F 이후 최근 매매 — Form 4 · 13D/13G · ARK 매일 (파싱 · 자기 회사 제외 · 지분 변화 · 신호 · 결과에 붙이기)"""
from datetime import date

from app.services import guru_recent as gr, gurus

FORM4 = """<?xml version="1.0"?><ownershipDocument><documentType>4</documentType>
<issuer><issuerCik>0001981599</issuerCik><issuerName>CVR PARTNERS</issuerName><issuerTradingSymbol>ctri</issuerTradingSymbol></issuer>
<reportingOwner><reportingOwnerId><rptOwnerCik>0000921669</rptOwnerCik><rptOwnerName>ICAHN CARL C</rptOwnerName></reportingOwnerId></reportingOwner>
<nonDerivativeTable>
<nonDerivativeTransaction><transactionDate><value>2026-11-13</value></transactionDate>
 <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
 <transactionAmounts><transactionShares><value>163261</value></transactionShares><transactionPricePerShare><value>21.84</value></transactionPricePerShare>
 <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
 <postTransactionAmounts><sharesOwnedFollowingTransaction><value>12672350</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
</nonDerivativeTransaction>
<nonDerivativeTransaction><transactionDate><value>2026-11-14</value></transactionDate>
 <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
 <transactionAmounts><transactionShares><value>1000</value></transactionShares><transactionPricePerShare><value>20.5</value></transactionPricePerShare></transactionAmounts>
 <postTransactionAmounts><sharesOwnedFollowingTransaction><value>12673350</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
</nonDerivativeTransaction>
<nonDerivativeTransaction><transactionDate><value>2026-11-15</value></transactionDate>
 <transactionCoding><transactionCode>G</transactionCode></transactionCoding>
 <transactionAmounts><transactionShares><value>50</value></transactionShares></transactionAmounts>
</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""

G13 = """<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g"><headerData><submissionType>SCHEDULE 13G/A</submissionType></headerData>
<formData><coverPageHeader><eventDateRequiresFilingThisStatement>09/30/2026</eventDateRequiresFilingThisStatement>
<issuerInfo><issuerCik>0001601830</issuerCik><issuerCusipNumber>75629V104</issuerCusipNumber><issuerName>Recursion Pharmaceuticals, Inc.</issuerName></issuerInfo>
</coverPageHeader><coverPageHeaderReportingPersonDetails><reportingPersonName>ARK</reportingPersonName>
<reportingPersonBeneficiallyOwnedAggregateNumberOfShares>45000000</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
<classPercent>8.36</classPercent></coverPageHeaderReportingPersonDetails></formData></edgarSubmission>"""


def test_parse_form4_only_owner_open_market():
    t = gr.parse_form4(FORM4, 921669)
    assert [(x["side"], x["date"], x["shares"], x["price"]) for x in t] == [("sell", "2026-11-13", 163261, 21.84), ("buy", "2026-11-14", 1000, 20.5)]
    assert t[0]["ticker"] == "CTRI" and t[0]["after"] == 12672350          # 증여(G)는 뺌
    assert gr.parse_form4(FORM4, 1067983) == []                             # 대가가 보고자가 아님 (그 회사가 발행회사인 공시)
    own = FORM4.replace("0001981599", "0000921669")
    assert gr.parse_form4(own, 921669) == []                                # 자기 회사 주식


def test_parse_13g_and_moves_pct_change():
    d = gr.parse_13dg(G13, 1697748)
    assert d == {"issuer": "Recursion Pharmaceuticals, Inc.", "issuer_cik": 1601830, "cusip": "75629V104", "pct": 8.36,
                 "shares": 45000000, "event_date": "2026-09-30"}
    assert gr.parse_13dg(G13, 1601830) is None                              # 자기 회사
    first = {"form": "SCHEDULE 13G", "acc": "a1", "filed": "2026-05-10", "data": {**d, "pct": 6.0}}
    amend = {"form": "SCHEDULE 13G/A", "acc": "a2", "filed": "2026-11-13", "data": d}
    f4 = {"form": "4", "acc": "a3", "filed": "2026-11-17", "data": gr.parse_form4(FORM4, 921669)}
    mv = gr.moves_from([amend, f4, first], {1601830: "RXRX"})
    assert [m["kind"] for m in mv] == ["sell", "buy", "stake_up", "stake_new"]   # 최신 순 (같은 날은 들어온 순)
    up = next(m for m in mv if m["kind"] == "stake_up")
    assert up["pct_prev"] == 6.0 and up["pct"] == 8.36 and up["ticker"] == "RXRX" and up["form"] == "13G/A"
    buys = gr.buy_moves(mv)
    assert [(m["kind"], m["ticker"]) for m in buys] == [("buy", "CTRI"), ("stake_up", "RXRX"), ("stake_new", "RXRX")]


def test_recent_filings_filters_forms_and_dates():
    sub = {"filings": {"recent": {"form": ["4", "13F-HR", "SCHEDULE 13D", "8-K", "4"], "accessionNumber": ["a", "b", "c", "d", "e"],
                                  "filingDate": ["2026-11-20", "2026-11-14", "2026-10-01", "2026-11-01", "2025-01-01"],
                                  "primaryDocument": ["x/ownership.xml", "", "x/primary_doc.xml", "", "o.xml"]}}}
    assert [f["acc"] for f in gr.recent_filings(sub, "2026-01-01")] == ["a", "c"]


ARK1 = 'date,fund,company,ticker,cusip,shares,"market value ($)",weight (%)\n' \
       '11/24/2026,ARKK,TESLA INC,TSLA,88160R101,"1,000,000","$400,000,000.00",10.00%\n' \
       '11/24/2026,ARKK,ROKU INC,ROKU,77543R102,"500,000","$50,000,000.00",2.00%\n' \
       '11/24/2026,ARKK,OPENAI SERIES C,,PPOPENAI,"10","$1.00",0.10%\n'
ARK2 = ARK1.replace("11/24/2026", "11/25/2026").replace('"1,000,000"', '"1,100,000"') \
    .replace('11/25/2026,ARKK,ROKU INC,ROKU,77543R102,"500,000","$50,000,000.00",2.00%\n', '') + \
    '11/25/2026,ARKK,PALANTIR,PLTR,69608A108,"20,000","$3,000,000.00",0.50%\n'


def test_ark_daily_moves():
    d1, h1 = gr.parse_ark_csv(ARK1)
    assert d1 == "2026-11-24" and set(h1) == {"TSLA", "ROKU"} and h1["TSLA"]["shares"] == 1_000_000   # 티커 없는 줄 제외
    d2, h2 = gr.parse_ark_csv(ARK2)
    snaps = {d1: gr.merge_funds([h1]), d2: gr.merge_funds([h2, {"TSLA": {"shares": 5.0, "value": 1.0, "company": "TESLA INC", "weight": 0}}])}
    mv = {m["ticker"]: m for m in gr.ark_moves(snaps)}
    assert mv["TSLA"]["kind"] == "buy" and mv["TSLA"]["change_pct"] == 10.0
    assert mv["ROKU"]["kind"] == "sell" and mv["ROKU"]["exit"] and mv["PLTR"]["new"]
    assert gr.ark_moves({d1: snaps[d1]}) == []                                  # 하루치만 있으면 비교 못 함
    small = {d1: {"A": {"shares": 100.0, "value": 1, "company": ""}}, d2: {"A": {"shares": 103.0, "value": 1, "company": ""}}}
    assert gr.ark_moves(small) == []                                            # 5% 미만 조정은 매매로 안 봄


def test_attach_moves_and_recent_signals():
    res = {"gurus": [{"key": "icahn", "period": "2026-09-30"}], "stocks": {}}
    moves = {"icahn": [{"date": "2026-11-17", "kind": "buy", "ticker": "CTRI", "form": "Form 4", "issuer": "CVR"},
                       {"date": "2026-08-01", "kind": "sell", "ticker": "IEP", "form": "Form 4", "issuer": "IEP"}]}
    gurus.attach_moves(res, moves, {"CTRI": "씨티알아이"}, today=date(2026, 11, 26))
    assert [m["ticker"] for m in res["moves"]["icahn"]] == ["CTRI"]            # 13F 기준일(9/30) 뒤만 화면에
    st = res["stocks"]["CTRI"]
    assert st["name"] == "씨티알아이" and st["n_recent_buys"] == 1 and st["recent"][0]["name"] == "칼 아이칸"
    assert "IEP" not in res["stocks"]                                           # 90일 지난 매매는 신호에 안 씀
    assert res["gurus"][0]["n_recent"] == 1 and res["gurus"][0]["recent_buys"] == 1
    sig = gurus.recent_signals(moves)
    assert sig == [{"key": "icahn", "ticker": "CTRI", "filed": "2026-11-17", "period": "2026-11-17", "weight": None, "src": "Form 4"}]


def test_clean_ticker():
    assert gr.clean_ticker("brk.b") == "BRK-B" and gr.clean_ticker("CTRI") == "CTRI"
    for bad in ("N/A", "NONE", "", None, "TDSPRV", "12345", "AB CD"):
        assert gr.clean_ticker(bad) is None
    x = FORM4.replace("<issuerTradingSymbol>ctri</issuerTradingSymbol>", "<issuerTradingSymbol>N/A</issuerTradingSymbol>")
    assert gr.parse_form4(x, 921669)[0]["ticker"] is None
    mv = gr.moves_from([{"form": "4", "acc": "z", "filed": "2026-11-20", "data": gr.parse_form4(x, 921669)}], {1981599: "CTRI"})
    assert mv[0]["ticker"] == "CTRI"                                              # 공시 티커가 없으면 SEC 회사 번호로
