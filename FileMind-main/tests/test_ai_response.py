"""Tests for the future AI adapter's strict, path-free JSON contract."""

import json
import unittest

from filemind.ai.response import parse_suggestions


class AIResponseTests(unittest.TestCase):
    def test_invalid_json_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "合法 JSON"):
            parse_suggestions("{oops", {"课程.pdf"})

    def test_model_path_and_invalid_category_are_rejected(self) -> None:
        path_suggestion = {
            "file_name": "课程.pdf", "category": "学习", "new_name": "课程.pdf",
            "reason": "课程资料", "target_path": "../../outside",
        }
        with self.assertRaisesRegex(ValueError, "目标路径"):
            parse_suggestions(json.dumps({"suggestions": [path_suggestion]}), {"课程.pdf"})

        invalid_category = {key: value for key, value in path_suggestion.items() if key != "target_path"}
        invalid_category["category"] = "../outside"
        with self.assertRaisesRegex(ValueError, "分类文件夹"):
            parse_suggestions(json.dumps({"suggestions": [invalid_category]}), {"课程.pdf"})

    def test_valid_suggestion_preserves_chinese_filename_extension(self) -> None:
        item = {"file_name": "课件.pdf", "category": "学习资料", "new_name": "数据结构复习.pdf", "reason": "名称更清楚"}

        suggestions = parse_suggestions(json.dumps({"suggestions": [item]}, ensure_ascii=False), {"课件.pdf"})

        self.assertEqual(suggestions["课件.pdf"].new_name, "数据结构复习.pdf")


if __name__ == "__main__":
    unittest.main()
