#!/usr/bin/env python3
"""Minimal deterministic Markdown-based consistency check and oracle gate.

No LLM calls, no third-party packages, no modification of production sources.
The analyzer verifies literal anchors only; it does NOT prove program behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

RULE_COLUMNS = ["ID", "仕様ファイル", "仕様アンカー", "出典SHA256", "実装ファイル",
                "実装アンカー", "期待値", "承認", "未決ID"]
QUESTION_COLUMNS = ["ID", "対象", "未決事項", "状態", "決定先"]
APPROVALS = {"pending", "approved", "blocked"}
QUESTION_STATES = {"OPEN", "DECIDED", "CANCELLED", "UNCONFIRMED", "未確認"}


class InputError(Exception):
    pass


def table(path: Path, headers: list[str]):
    """Read one simple Markdown table with exact column headers."""
    if not path.is_file():
        raise InputError(f"ファイルがありません: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    for start, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cols = [x.strip() for x in line.strip().strip("|").split("|")]
        if cols != headers:
            continue
        if start + 1 >= len(lines):
            raise InputError(f"表の区切り行がありません: {path}")
        sep = [x.strip() for x in lines[start + 1].strip().strip("|").split("|")]
        if len(sep) != len(headers) or any(not re.fullmatch(r":?-{3,}:?", x) for x in sep):
            raise InputError(f"表の区切り行が不正: {path}:{start + 2}")
        result = []
        for i in range(start + 2, len(lines)):
            if not lines[i].startswith("|"):
                break
            cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
            if len(cells) != len(headers):
                raise InputError(f"列数が不正: {path}:{i + 1}")
            result.append((dict(zip(headers, cells)), i))
        return lines, result
    raise InputError(f"指定された見出しのMarkdown表がありません: {path}")


def source_path(root: Path, value: str) -> Path:
    if not value or value == "-" or Path(value).is_absolute():
        raise InputError(f"無効な相対パス: {value!r}")
    target = (root / value).resolve()
    if not target.is_relative_to(root.resolve()):
        raise InputError(f"リポジトリ外への参照は不可: {value}")
    return target


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_literal(root: Path, filename: str, anchor: str):
    if filename == "-" or anchor == "-":
        return "UNVERIFIED", "検査箇所が未登録"
    try:
        data = source_path(root, filename).read_text(encoding="utf-8")
    except (InputError, OSError, UnicodeError) as exc:
        return "UNVERIFIED", f"ファイルが読めない: {exc}"
    count = data.count(anchor)
    if count == 1:
        return "ANCHOR_FOUND", "指定した文字列が1回存在する（動作の証明ではない）"
    return "DRIFT", f"文字列の出現回数が{count}回（0または複数のため再確認）"


def load_questions(root: Path):
    _, rows = table(root / "test-gate-mvp" / "OPEN_QUESTIONS.md", QUESTION_COLUMNS)
    questions = {}
    for row, _ in rows:
        name = row["ID"]
        if name.startswith("Q-EXAMPLE"):
            continue
        if name in questions or not name:
            raise InputError(f"未決IDが重複または空: {name}")
        if row["状態"] not in QUESTION_STATES:
            raise InputError(f"未決事項の状態が不明: {name}={row['状態']}")
        questions[name] = row["状態"]
    return questions


def read_rules(root: Path):
    path = root / "test-gate-mvp" / "TEST_RULES.md"
    lines, rows = table(path, RULE_COLUMNS)
    ids = set()
    for row, _ in rows:
        rid = row["ID"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", rid) or rid in ids:
            raise InputError(f"無効または重複したルールID: {rid}")
        ids.add(rid)
        if row["承認"] not in APPROVALS:
            raise InputError(f"承認値が不正: {rid}={row['承認']}")
        value = row["出典SHA256"]
        if value != "-" and not re.fullmatch(r"[0-9a-f]{64}", value):
            raise InputError(f"SHA256の形式が不正: {rid}")
        if not row["期待値"] or row["期待値"] == "-":
            raise InputError(f"期待値がありません: {rid}")
    return path, lines, rows


def decide(root: Path, row: dict, questions: dict):
    reasons = []
    spec_status, spec_reason = inspect_literal(root, row["仕様ファイル"], row["仕様アンカー"])
    impl_status, impl_reason = inspect_literal(root, row["実装ファイル"], row["実装アンカー"])

    if row["承認"] != "approved":
        reasons.append("未承認: " + row["承認"])
    if spec_status != "ANCHOR_FOUND":
        reasons.append("仕様原文を一意に確認できない: " + spec_reason)
    try:
        current = digest(source_path(root, row["仕様ファイル"]).read_bytes())
    except (InputError, OSError) as exc:
        current = None
        reasons.append(f"仕様ファイルを読めない: {exc}")
    if row["出典SHA256"] == "-":
        reasons.append("出典SHA256が未登録")
    elif current != row["出典SHA256"]:
        reasons.append("承認時から仕様ファイルが変更された")
    ids = [] if row["未決ID"] == "-" else [x.strip() for x in row["未決ID"].split(",")]
    for qid in ids:
        if qid not in questions:
            reasons.append(f"未決IDの参照先がない: {qid}")
        elif questions[qid] != "DECIDED":
            reasons.append(f"未決事項が未解決: {qid}({questions[qid]})")
    # An implementation drift never invalidates a valid specification oracle.
    decision = "HOLD" if reasons else "ALLOW"
    return spec_status, impl_status, decision, reasons, impl_reason


def stamp(root: Path, rule_id: str):
    path, lines, rows = read_rules(root)
    for row, index in rows:
        if row["ID"] != rule_id:
            continue
        if row["承認"] != "pending":
            raise InputError("再スタンプはpending行のみ。まず人間が承認を取り消してください")
        status, reason = inspect_literal(root, row["仕様ファイル"], row["仕様アンカー"])
        if status != "ANCHOR_FOUND":
            raise InputError(f"仕様アンカーの確認に失敗: {reason}")
        value = digest(source_path(root, row["仕様ファイル"]).read_bytes())
        row["出典SHA256"] = value
        lines[index] = "| " + " | ".join(row[k] for k in RULE_COLUMNS) + " |"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{rule_id}: 出典SHA256を更新しました。承認状態はpendingのままです")
        return 0
    raise InputError(f"指定したルールがありません: {rule_id}")


def run(root: Path, strict: bool):
    _, _, rows = read_rules(root)
    questions = load_questions(root)
    print("| ID | Analyzer:仕様 | Analyzer:実装 | Gate | 理由 |")
    print("| --- | --- | --- | --- | --- |")
    failed = not rows
    if not rows:
        print("| - | UNVERIFIED | UNVERIFIED | HOLD | ルールが未登録 |")
    for row, _ in sorted(rows, key=lambda item: item[0]["ID"]):
        spec, implementation, gate, reasons, impl_reason = decide(root, row, questions)
        if implementation != "ANCHOR_FOUND":
            reasons.append("実装: " + impl_reason)
        reason = " / ".join(reasons) or "出典・承認が有効（意味的妥当性は人間承認）"
        reason = reason.replace("|", "/").replace("\n", " ")
        print(f"| {row['ID']} | {spec} | {implementation} | {gate} | {reason} |")
        if gate != "ALLOW" or implementation == "DRIFT":
            failed = True
    return 1 if strict and failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Markdownベースの最小Analyzer + Gate")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--stamp", metavar="RULE_ID", help="pending行に現在の仕様SHA256を記録")
    parser.add_argument("--strict", action="store_true", help="HOLD・実装DRIFT・ルール0件は終了1")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        return stamp(root, args.stamp) if args.stamp else run(root, args.strict)
    except (InputError, OSError, UnicodeError) as exc:
        print(f"INPUT_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
