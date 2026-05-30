import json
from pathlib import Path

p = Path(r'C:\Users\胖子熊\MyProject\FreeArk\scripts\analysis\capture_raw_3-1-702.jsonl')
recs = [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines()]

print('=== 空 attrTag 出现的样例 ===')
empty_count_per_msg = []
for i, r in enumerate(recs):
    pl = json.loads(r['payload_text'])
    d = pl['payload']['data']
    empty = [it for it in d['items'] if it['attrTag'] == '']
    if empty:
        empty_count_per_msg.append((i+1, pl['header']['messageId'], d['deviceSn'], d['productCode'], len(d['items']), len(empty)))

print(f'含空 attrTag 的消息数: {len(empty_count_per_msg)}')
for row in empty_count_per_msg[:5]:
    print(f'  #{row[0]} msgId={row[1]} deviceSn={row[2]} productCode={row[3]} items_len={row[4]} empty_count={row[5]}')

# 完整展示第一条含空 attrTag 的消息
if empty_count_per_msg:
    idx = empty_count_per_msg[0][0] - 1
    print('\n[完整 dump]')
    print(json.dumps(json.loads(recs[idx]['payload_text']), ensure_ascii=False, indent=2))

print('\n=== items 长度最大的消息（26 项） ===')
mx = max(recs, key=lambda r: len(json.loads(r['payload_text'])['payload']['data']['items']))
print(json.dumps(json.loads(mx['payload_text']), ensure_ascii=False, indent=2))

print('\n=== items=12 的一条样例 ===')
for r in recs:
    pl = json.loads(r['payload_text'])
    if len(pl['payload']['data']['items']) == 12:
        print(json.dumps(pl, ensure_ascii=False, indent=2))
        break

print('\n=== 0.1s 突发段相邻消息（间隔最小那段） ===')
prev_ts = None
for i, r in enumerate(recs):
    if prev_ts and (r['ts'] - prev_ts) < 200:  # 小于 200ms
        pl = json.loads(r['payload_text'])
        print(f'#{i+1} +{r["ts"]-prev_ts}ms msgId={pl["header"]["messageId"]} dSn={pl["payload"]["data"]["deviceSn"]} pCode={pl["payload"]["data"]["productCode"]} items_len={len(pl["payload"]["data"]["items"])}')
    prev_ts = r['ts']
