#!/usr/bin/env python3
"""
process_data.py - _rawdata/leisure_raw.json(영업 중 민간 체육시설)을 Jekyll 페이지 생성용 JSON(시도별 shard)과
검색 인덱스로 가공한다.

종목(cat) 분류: 체육도장은 업태구분명(태권도/권투/합기도/유도/검도/기타)으로 쪼개 "OO동 태권도" 같은 검색에 대응.
출력: _rawdata/lei_{시도}.json, search_index.json
"""
import json, re, sys, hashlib
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
RAW = ROOT / "_rawdata" / "leisure_raw.json"
RAWDATA_DIR = ROOT / "_rawdata"
SEARCH_INDEX_OUT = ROOT / "search_index.json"

DO_MAP = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
    "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주", "제주도": "제주",
}

# (cat key) -> (slug, 라벨, 아이콘)
CATS = {
    "골프연습장": ("golf-range", "골프연습장", "⛳"),
    "당구장": ("billiard", "당구장", "🎱"),
    "수영장": ("pool", "수영장", "🏊"),
    "골프장": ("golf-course", "골프장", "🏌️"),
    "스키장": ("ski", "스키장", "⛷️"),
    "태권도": ("taekwondo", "태권도장", "🥋"),
    "복싱": ("boxing", "복싱장", "🥊"),
    "합기도": ("hapkido", "합기도장", "🥋"),
    "유도": ("judo", "유도장", "🥋"),
    "검도": ("kumdo", "검도장", "🤺"),
    "체육도장": ("dojang", "체육도장", "🥋"),
}
DOJO_MAP = {"태권도": "태권도", "권투": "복싱", "합기도": "합기도", "유도": "유도", "검도": "검도"}
SRC_CAT = {"golf_practice_ranges": "골프연습장", "billiard_halls": "당구장", "swimming_pools": "수영장",
           "golf_courses": "골프장", "ski_resorts": "스키장"}

DONG_TOKEN = re.compile(r"^[가-힣][가-힣0-9]*(?:동|읍|면)$|^[가-힣]+\d+가$")
BUILDING_LABEL = re.compile(r"^[가나다라마바사아자차카타파하]동$")


def clean(s):
    return re.sub(r"\s+", " ", str(s or "").strip())


def split_address(addr):
    toks = addr.split()
    if len(toks) < 2:
        return None, None, []
    sido_full = toks[0]
    if sido_full == "세종특별자치시":
        return sido_full, "세종시", toks[1:]
    sg = toks[1]
    rest = toks[2:]
    if sg.endswith("시") and rest and rest[0].endswith("구") and len(rest[0]) > 1:
        sg = f"{sg} {rest[0]}"
        rest = rest[1:]
    return sido_full, sg, rest


def find_dong(tokens):
    for t in tokens[:4]:
        t = t.strip("(),")
        if DONG_TOKEN.match(t) and not BUILDING_LABEL.match(t):
            return t
    return None


def dong_from_paren(addr):
    for m in re.finditer(r"\(([^)]*)\)", addr):
        for part in re.split(r"[,\s]+", m.group(1)):
            if DONG_TOKEN.match(part) and not BUILDING_LABEL.match(part):
                return part
    return None


def fmt_tel(t):
    d = re.sub(r"\D", "", t or "")
    if len(d) < 8:
        return ""
    if d.startswith("02"):
        return f"02-{d[2:-4]}-{d[-4:]}" if len(d) >= 9 else ""
    if len(d) in (10, 11) and d.startswith("0"):
        return f"{d[:3]}-{d[3:-4]}-{d[-4:]}"
    if len(d) == 8:
        return f"{d[:4]}-{d[4:]}"
    return ""


def make_slug(name, addr):
    base = re.sub(r"[^\w가-힣\s-]", "", name).strip()
    base = re.sub(r"\s+", "-", base)
    base = re.sub(r"-+", "-", base)[:30].strip("-")
    h = hashlib.md5(f"{name}|{addr}".encode("utf-8")).hexdigest()[:6]
    return f"{base}-{h}" if base else h


def main():
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    items, seen, skipped = [], Counter(), Counter()
    dedupe = set()
    for src, rows in raw.items():
        for r in rows:
            name = clean(r.get("n"))
            lot, road = clean(r.get("lot")), clean(r.get("road"))
            addr = road or lot
            if not name or not addr:
                skipped["no_name_addr"] += 1
                continue
            if src == "martial_arts_dojo":
                cat = DOJO_MAP.get(clean(r.get("type")), "체육도장")
            else:
                cat = SRC_CAT[src]
            sido_full, sg, rest = split_address(lot or road)
            if not sido_full:
                skipped["bad_addr"] += 1
                continue
            if sido_full == "전남광주통합특별시":
                do = "광주" if (sg or "").endswith("구") else "전남"
            else:
                do = DO_MAP.get(sido_full)
            if not do or not sg:
                skipped["no_sido"] += 1
                continue
            dong = find_dong(rest) or dong_from_paren(road) or "기타"
            dkey = (name, addr, cat, clean(r.get("type")) if src == "golf_courses" else "")
            if dkey in dedupe:
                skipped["duplicate"] += 1
                continue
            dedupe.add(dkey)
            slug = make_slug(name, addr)
            seen[slug] += 1
            if seen[slug] > 1:
                slug = f"{slug}-{seen[slug]}"
            cs, label, icon = CATS[cat]
            items.append({
                "slug": slug, "facilityName": name, "cat": cat, "catSlug": cs, "catLabel": label, "catIcon": icon,
                "doShort": do, "sigungu": sg, "sgSlug": sg.replace(" ", "-"), "dong": dong,
                "road": road, "lot": lot, "tel": fmt_tel(r.get("tel")),
                "lat": r.get("lat") or "", "lng": r.get("lng") or "",
                "permit": clean(r.get("permit")), "upd": clean(r.get("upd")),
                "ownership": clean(r.get("ownership")), "leaders": clean(r.get("leaders")) if clean(r.get("leaders")) not in ("0", "") else "",
                "members": clean(r.get("members")) if clean(r.get("members")) not in ("0", "") else "",
                "subtype": clean(r.get("type")) if src == "golf_courses" and clean(r.get("type")) not in ("", "없음", "골프장") else "",
            })

    by_dong_cat = defaultdict(list)
    for i in items:
        by_dong_cat[(i["doShort"], i["sigungu"], i["dong"], i["cat"])].append(i)
    for lst in by_dong_cat.values():
        lst.sort(key=lambda x: (x["permit"] or "9999", x["slug"]))
        for rank, i in enumerate(lst, 1):
            i["catDongCount"] = len(lst)
            i["catDongRank"] = rank

    RAWDATA_DIR.mkdir(parents=True, exist_ok=True)
    for old in RAWDATA_DIR.glob("lei_*.json"):
        old.unlink()
    by_do = defaultdict(list)
    for i in items:
        by_do[i["doShort"]].append(i)
    for do, group in by_do.items():
        out = RAWDATA_DIR / f"lei_{do}.json"
        out.write_text(json.dumps(group, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  {do}: {len(group)}곳 → {out.name} ({out.stat().st_size/1024/1024:.1f}MB)")

    cats = Counter(i["cat"] for i in items)
    print(f"\n총 {len(items):,}곳 (제외 {dict(skipped)}), 종목별: {dict(cats)}")
    dongs = Counter((i["doShort"], i["sigungu"], i["dong"]) for i in items)
    catdongs = Counter((i["cat"], i["doShort"], i["sigungu"], i["dong"]) for i in items)
    no_dong = sum(1 for i in items if i["dong"] == "기타")
    print(f"시군구 {len({(i['doShort'], i['sigungu']) for i in items})}개, 동 {len(dongs)}개(≥3곳 {sum(1 for v in dongs.values() if v >= 3)}), 종목×동 {len(catdongs)}개(≥2곳 {sum(1 for v in catdongs.values() if v >= 2)}), 동 기타 {no_dong} ({no_dong/len(items)*100:.1f}%)")

    index = [{"n": i["facilityName"], "s": i["slug"], "do": i["doShort"], "sg": i["sigungu"], "dg": i["dong"], "c": i["catLabel"]} for i in items]
    SEARCH_INDEX_OUT.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"검색 인덱스 {len(index):,}건 ({SEARCH_INDEX_OUT.stat().st_size/1024/1024:.1f}MB)")


if __name__ == "__main__":
    main()
