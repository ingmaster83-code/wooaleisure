#!/usr/bin/env python3
"""
fetch_leisure.py - 행정안전부 '생활' 인허가 시리즈(LOCALDATA) 중 민간 체육시설업 CSV를 내려받아
영업 중인 시설만 정규화해 _rawdata/leisure_raw.json 으로 저장한다.

- CSV는 CP949, 좌표는 Bessel 중부원점 TM(EPSG:5174) -> pyproj로 WGS84 변환
- 영업상태명 '영업/정상'만 사용
- 업종별 원본 CSV는 data/raw/{key}.csv 에 보관(gitignore)

사용법: python scripts/fetch_leisure.py [--only golf_practice_ranges,billiard_halls]
"""
import csv, io, json, sys, argparse, time
from pathlib import Path
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT = ROOT / "_rawdata" / "leisure_raw.json"

# key: (한글명, slug)
CATEGORIES = {
    "golf_practice_ranges": "골프연습장",
    "golf_courses": "골프장",
    "billiard_halls": "당구장",
    "martial_arts_dojo": "체육도장",
    "swimming_pools": "수영장",
    "ski_resorts": "스키장",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
OPEN = "영업/정상"


def download(key):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{key}.csv"
    url = f"https://file.localdata.go.kr/file/download/{key}/info"
    h = dict(HEADERS, Referer=f"https://file.localdata.go.kr/file/{key}/info")
    for attempt in range(3):
        try:
            r = requests.get(url, headers=h, timeout=300)
            r.raise_for_status()
            if len(r.content) < 2000:
                raise ValueError(f"응답이 너무 작음({len(r.content)}B)")
            path.write_bytes(r.content)
            return path
        except Exception as e:
            print(f"  [{key}] 재시도 {attempt + 1}: {e}")
            time.sleep(3)
    return None


def read_rows(path):
    raw = path.read_bytes()
    try:
        text = raw.decode("cp949")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--no-download", action="store_true", help="data/raw/*.csv 가 이미 있으면 재사용")
    args = ap.parse_args()
    keys = [k for k in CATEGORIES if not args.only or k in args.only.split(",")]

    from pyproj import Transformer
    tf = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)

    result = {}
    for key in keys:
        path = RAW_DIR / f"{key}.csv" if (args.no_download and (RAW_DIR / f"{key}.csv").exists()) else download(key)
        if not path:
            print(f"[{key}] 다운로드 실패")
            continue
        rows = read_rows(path)
        cols = list(rows[0].keys()) if rows else []
        opens = [r for r in rows if (r.get("영업상태명") or "").strip() == OPEN]
        out = []
        for r in opens:
            x = (r.get("좌표정보(X)") or r.get("좌표정보(x)") or "").strip()
            y = (r.get("좌표정보(Y)") or r.get("좌표정보(y)") or "").strip()
            lat = lng = ""
            try:
                if x and y:
                    lo, la = tf.transform(float(x), float(y))
                    if 33 <= la <= 39 and 124 <= lo <= 132:
                        lat, lng = round(la, 6), round(lo, 6)
            except ValueError:
                pass
            out.append({
                "n": (r.get("사업장명") or "").strip(),
                "road": (r.get("도로명주소") or "").strip(),
                "lot": (r.get("지번주소") or "").strip(),
                "tel": (r.get("전화번호") or "").strip(),
                "permit": (r.get("인허가일자") or "").strip(),
                "upd": (r.get("최종수정시점") or "").strip()[:10],
                "type": (r.get("업태구분명") or r.get("세부업종명") or r.get("문화체육업종명") or "").strip(),
                "ownership": (r.get("공사립구분명") or "").strip(),
                "bldArea": (r.get("건축물연면적") or "").strip(),
                "members": (r.get("회원모집총인원") or "").strip(),
                "leaders": (r.get("지도자수") or "").strip(),
                "corp": (r.get("법인명") or "").strip(),
                "lat": lat, "lng": lng,
            })
        result[key] = out
        has_xy = sum(1 for o in out if o["lat"])
        has_tel = sum(1 for o in out if o["tel"])
        print(f"[{key}] {CATEGORIES[key]}: 전체 {len(rows):,} / 영업 {len(out):,} / 좌표 {has_xy:,} / 전화 {has_tel:,} / 컬럼 {len(cols)}", flush=True)
        print("   컬럼:", cols)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"저장: {OUT} ({OUT.stat().st_size/1e6:.1f}MB)")


if __name__ == "__main__":
    main()
