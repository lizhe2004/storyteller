from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


_AGES = {"child", "teen", "young_adult", "middle_aged", "senior", "unknown"}
_GENDERS = {"male", "female", "unknown"}
_TIMBRE_ALIASES = {
    "warm": "温暖", "gentle": "温柔", "soft": "柔和", "clear": "清晰",
    "bright": "明亮", "clear and bright": "清晰明亮", "sweet": "甜美",
    "deep": "浑厚", "rich": "饱满", "calm": "沉稳", "lively": "活泼",
    "natural": "自然", "warm and gentle": "温暖柔和", "low": "低沉",
}


def normalize_voice_analysis(payload):
    payload = payload if isinstance(payload, dict) else {}
    age = payload.get("observed_age", payload.get("age", "unknown"))
    age_aliases = {
        "adult": "young_adult", "young adult": "young_adult", "middle-aged": "middle_aged",
        "儿童": "child", "小孩": "child", "少年": "teen", "青少年": "teen",
        "青年": "young_adult", "年轻人": "young_adult", "中年": "middle_aged", "老年": "senior",
    }
    age = age_aliases.get(str(age).strip().lower(), str(age).strip().lower())
    gender = str(payload.get("observed_gender", payload.get("gender", "unknown"))).strip().lower()
    gender = {"男": "male", "男性": "male", "女": "female", "女性": "female"}.get(gender, gender)
    result = dict(payload)
    result["observed_age"] = age if age in _AGES else "unknown"
    result["observed_gender"] = gender if gender in _GENDERS else "unknown"
    timbre = payload.get("timbre", [])
    timbre = timbre if isinstance(timbre, list) else [timbre]
    result["timbre"] = [_TIMBRE_ALIASES.get(str(item).strip().lower(), str(item).strip()) for item in timbre]
    confidence = payload.get("confidence", 0.0) or 0.0
    if isinstance(confidence, str):
        confidence = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(confidence.strip().lower(), 0.0)
    result["confidence"] = max(0.0, min(float(confidence), 1.0))
    return result


def normalize_match_result(value):
    if isinstance(value, (int, float)):
        return {"overall": max(0.0, min(float(value), 1.0))}
    if isinstance(value, dict):
        result = dict(value)
        overall = result.get("overall", 0.0)
        if isinstance(overall, str):
            overall = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(overall.lower(), 0.0)
        try:
            result["overall"] = max(0.0, min(float(overall), 1.0))
        except (TypeError, ValueError):
            result["overall"] = 0.0
        return result
    return {"overall": 0.0}


def normalize_voice_summary(payload):
    result = dict(payload) if isinstance(payload, dict) else {}
    result["catalog_match"] = normalize_match_result(result.get("catalog_match"))
    result["role_match"] = normalize_match_result(result.get("role_match"))
    return result


class GeminiAudioAnalyzer:
    def __init__(self, api_key=None, model_sample="gemini-3.5-flash-lite", model_summary="gemini-3.5-flash", session=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model_sample = model_sample
        self.model_summary = model_summary
        self.session = session

    def _request(self, model, contents, *, include_thoughts=False):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        payload = {"contents": [{"parts": contents}], "generationConfig": {"responseMimeType": "application/json"}}
        if include_thoughts:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 1024, "includeThoughts": True}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(model),
            data=body, headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key}, method="POST")
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
        parts = data["candidates"][0]["content"]["parts"]
        thoughts = "\n".join(p.get("text", "") for p in parts if p.get("thought"))
        answer = "\n".join(p.get("text", "") for p in parts if not p.get("thought"))
        return json.loads(answer), thoughts, data

    def analyze_sample(self, sample, include_thoughts=False):
        audio = Path(sample["audio_path"])
        prompt = ("只根据音频本身分析中文 TTS 声音，不要参考音色名称、角色描述或台词。"
                  "返回 JSON：observed_gender、observed_age、timbre、energy、speech_rate、"
                  "suitable_roles、confidence、evidence。年龄只能使用 child/teen/young_adult/"
                  "middle_aged/senior/unknown；evidence 写简短可观察依据。")
        payload, thoughts, raw = self._request(self.model_sample, [
            {"text": prompt},
            {"inline_data": {"mime_type": "audio/mpeg", "data": base64.b64encode(audio.read_bytes()).decode("ascii")}},
        ], include_thoughts=include_thoughts)
        return {"raw_response": raw, "normalized_result": normalize_voice_analysis(payload), "thought_summary": thoughts or None}

    def analyze_samples(self, samples, include_thoughts=False):
        """Analyze all samples for one voice in a single multimodal request."""
        if not samples:
            return {}
        prompt = ("只根据下面带 sample_id 标记的中文 TTS 音频片段分析声音。"
                  "请对每个 sample_id 分别返回结果，不要参考音色名称、角色描述或台词。"
                  "返回 JSON：samples 数组，每项包含 sample_id、observed_gender、observed_age、"
                  "timbre（必须使用中文形容词，如温柔、清晰、明亮、浑厚）、energy、speech_rate、suitable_roles、confidence、evidence。"
                  "年龄只能使用 child/teen/young_adult/middle_aged/senior/unknown；"
                  "evidence 写简短可观察依据。\n")
        parts = [{"text": prompt}]
        for sample in samples:
            audio = Path(sample["audio_path"])
            parts.append({"text": "下面是 {}：".format(sample["sample_id"])})
            parts.append({"inline_data": {"mime_type": "audio/mpeg", "data": base64.b64encode(audio.read_bytes()).decode("ascii")}})
        payload, thoughts, raw = self._request(self.model_sample, parts, include_thoughts=include_thoughts)
        observations = payload.get("samples", []) if isinstance(payload, dict) else []
        by_id = {item.get("sample_id"): item for item in observations if isinstance(item, dict) and item.get("sample_id")}
        # Models sometimes preserve the generated hash but drop the `sample_` prefix.
        by_id.update({"sample_" + key: value for key, value in list(by_id.items()) if isinstance(key, str) and not key.startswith("sample_")})
        if len(observations) == len(samples):
            by_id.update({sample["sample_id"]: item for sample, item in zip(samples, observations)})
        results = {}
        for sample in samples:
            item = by_id.get(sample["sample_id"])
            if item is None:
                raise ValueError("Gemini batch response missing {}".format(sample["sample_id"]))
            results[sample["sample_id"]] = {
                "raw_response": raw,
                "normalized_result": normalize_voice_analysis(item),
                "thought_summary": thoughts or None,
            }
        return results

    def analyze_voice(self, samples, catalog_snapshot, include_thoughts=False):
        """Analyze one voice end-to-end from raw audio in one Lite request."""
        if not samples:
            raise ValueError("音色没有可分析的样本")
        prompt = ("请分析同一个 TTS 音色的多个中文语音样本。必须严格按两个阶段工作："
                  "第一阶段只根据音频判断实际声音特征；第二阶段再结合角色信息和音色库声明进行匹配。"
                  "返回 JSON，包含 samples 和 voice_summary。samples 数组逐项包含 sample_id、"
                  "observed_gender、observed_age、timbre（必须使用中文）、energy、speech_rate、"
                  "confidence、evidence；voice_summary 的 observed_profile 优先返回对象，包含 gender、age、timbre（中文数组）、energy、speech_rate；"
                  "voice_summary 还包含 catalog_match、role_match、suggestions、evidence、"
                  "role_match 必须包含 overall、matched_traits、mismatches、risk_level、details；"
                  "mismatches 必须列出音色与历史角色不匹配或存在风险的具体地方，没有问题时返回空数组。"
                  "additional_traits（声明之外观察到的稳定特征数组）、catalog_enrichment。"
                  "catalog_enrichment 必须包含 recommended_tags、recommended_description、missing_from_catalog。"
                  "只把多个样本都能观察到或有明确证据的特征列为 additional_traits，不要把已有声明原样重复。"
                  "catalog_match 和 role_match 必须包含 0 到 1 的 overall。\n")
        context = []
        for sample in samples:
            context.append({
                "sample_id": sample["sample_id"], "character_name": sample.get("character_name"),
                "character_description": sample.get("character_description", ""),
                "character_gender": sample.get("character_gender"),
                "character_age": sample.get("character_age"),
                "line_type": sample.get("line_type"), "text": sample.get("text", ""),
            })
        prompt += json.dumps({"samples_context": context, "catalog_snapshot": catalog_snapshot or {}}, ensure_ascii=False)
        parts = [{"text": prompt}]
        for sample in samples:
            audio = Path(sample["audio_path"])
            parts.extend([
                {"text": "音频样本 {}：".format(sample["sample_id"])},
                {"inline_data": {"mime_type": "audio/mpeg", "data": base64.b64encode(audio.read_bytes()).decode("ascii")}},
            ])
        payload, thoughts, raw = self._request(self.model_sample, parts, include_thoughts=include_thoughts)
        observations = payload.get("samples", []) if isinstance(payload, dict) else []
        by_id = {item.get("sample_id"): item for item in observations if isinstance(item, dict) and item.get("sample_id")}
        by_id.update({"sample_" + key: value for key, value in list(by_id.items()) if isinstance(key, str) and not key.startswith("sample_")})
        if len(observations) == len(samples):
            by_id.update({sample["sample_id"]: item for sample, item in zip(samples, observations)})
        results = {}
        for sample in samples:
            item = by_id.get(sample["sample_id"])
            if item is None:
                raise ValueError("Gemini voice response missing {}".format(sample["sample_id"]))
            results[sample["sample_id"]] = {"raw_response": raw, "normalized_result": normalize_voice_analysis(item), "thought_summary": thoughts or None}
        return {"samples": results, "summary": {"raw_response": raw, "normalized_result": normalize_voice_summary(payload.get("voice_summary", {})), "thought_summary": thoughts or None}}

    def summarize_voice(self, samples, catalog_snapshot):
        prompt = ("根据以下多个音频样本的独立分析结果，汇总稳定音色特征，并对比音色库声明和历史角色使用。"
                  "只返回 JSON，包含 observed_profile、catalog_match、role_match、suggestions、evidence。"
                  "catalog_match 和 role_match 必须包含 overall（0到1）。suggestions 是字符串数组。\n")
        prompt += json.dumps({
            "samples": [{"analysis": s.get("normalized_result", s),
                         "character_name": s.get("character_name"),
                         "character_description": s.get("character_description"),
                         "text": s.get("text")} for s in samples],
            "catalog_snapshot": catalog_snapshot,
        }, ensure_ascii=False)
        payload, thoughts, raw = self._request(self.model_summary, [{"text": prompt}])
        return {"raw_response": raw, "normalized_result": normalize_voice_summary(payload), "thought_summary": thoughts or None}
