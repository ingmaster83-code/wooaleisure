#!/usr/bin/env bash
# 월간 데이터 갱신: LOCALDATA 다운로드 -> 가공(_rawdata/lei_*.json, search_index.json 재생성).
# 결과물은 커밋하지 않고 같은 워크플로의 Jekyll 빌드에만 쓴다(저장소 용량 증가 방지).
# 항목 수가 이전 대비 90%~130% 밖이면 실패시켜 배포를 막는다.
set -euo pipefail
cd "$(dirname "$0")/.."

before=$(python scripts/count_rawdata.py lei_)
python scripts/fetch_leisure.py
python scripts/process_data.py
after=$(python scripts/count_rawdata.py lei_)
echo "항목 수: 갱신 전 ${before} -> 갱신 후 ${after}"

if [ "${before}" -gt 0 ]; then
  if [ $((after * 100)) -lt $((before * 90)) ] || [ $((after * 100)) -gt $((before * 130)) ]; then
    echo "::error::항목 수가 비정상적으로 변했습니다(허용 90%~130%). 배포를 중단합니다."
    exit 1
  fi
fi
