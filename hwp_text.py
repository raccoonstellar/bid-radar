# -*- coding: utf-8 -*-
"""
hwp_text.py — HWP 5.0 (한글 2002~) 본문 텍스트 추출, 순수 파이썬 (vendor/olefile 사용)
pyhwp(hwp5txt) 없이도 동작하도록 만든 최소 구현. 표 안 텍스트도 문단 단위로 나온다.
- 배포용(암호화) 문서는 지원하지 않음 → 빈 문자열 + 사유
- 구형 HWP 3.x 는 미지원
"""
import io, zlib, struct

def _ole():
    import olefile  # vendor/ 에서 로드됨
    return olefile

# 문자 컨트롤 분류 (HWP 5.0 스펙 §문단 텍스트)
_CHAR_1  = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}      # 1 워드
_INLINE  = {4, 5, 6, 7, 8, 9, 19, 20}                        # 8 워드
_EXTEND  = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23} # 8 워드
_TAG_PARA_TEXT = 0x10 + 51

def _para_text(payload: bytes) -> str:
    out = []
    i, n = 0, len(payload) - 1
    while i < n:
        code = payload[i] | (payload[i + 1] << 8)
        if code < 32:
            if code in _CHAR_1:
                if code in (10, 13): out.append("\n")
                i += 2
            else:
                i += 16
            continue
        out.append(chr(code)) if 0xD800 > code or code > 0xDFFF else out.append(" ")
        i += 2
    return "".join(out)

def _records(data: bytes):
    i, n = 0, len(data)
    while i + 4 <= n:
        hdr = struct.unpack_from("<I", data, i)[0]; i += 4
        tag, size = hdr & 0x3FF, (hdr >> 20) & 0xFFF
        if size == 0xFFF:
            if i + 4 > n: break
            size = struct.unpack_from("<I", data, i)[0]; i += 4
        yield tag, data[i:i + size]
        i += size

def extract(data: bytes) -> tuple[str, str]:
    """(text, note). note 는 실패·제한 사유"""
    olefile = _ole()
    if not olefile.isOleFile(io.BytesIO(data)):
        return "", "OLE 형식 아님 (HWP 3.x/손상)"
    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        if not ole.exists("FileHeader"): return "", "FileHeader 없음"
        fh = ole.openstream("FileHeader").read()
        flags = struct.unpack_from("<I", fh, 36)[0]
        compressed, encrypted, distributed = flags & 1, flags & 2, flags & 4
        if encrypted: return "", "암호 설정 문서"
        if distributed: return _prv(ole), "배포용 문서 — 미리보기 텍스트만"
        secs = sorted([e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText" and e[1].startswith("Section")],
                      key=lambda e: int(e[1][7:] or 0))
        if not secs: return _prv(ole), "BodyText 없음 — 미리보기 텍스트만"
        parts = []
        for e in secs:
            raw = ole.openstream("/".join(e)).read()
            if compressed:
                try: raw = zlib.decompress(raw, -15)
                except Exception:
                    try: raw = zlib.decompressobj(-15).decompress(raw)
                    except Exception: continue
            for tag, payload in _records(raw):
                if tag == _TAG_PARA_TEXT:
                    t = _para_text(payload)
                    if t.strip(): parts.append(t)
        text = "\n".join(parts)
        return text, ("" if text.strip() else "본문 텍스트 없음")
    finally:
        ole.close()

def _prv(ole) -> str:
    try:
        if ole.exists("PrvText"): return ole.openstream("PrvText").read().decode("utf-16le", "ignore")
    except Exception: pass
    return ""

if __name__ == "__main__":
    import sys
    t, note = extract(open(sys.argv[1], "rb").read())
    print(note or f"{len(t)}자", file=sys.stderr); print(t[:3000])
