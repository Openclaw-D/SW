import assert from "node:assert/strict";
import test from "node:test";

import { formatCanonicalText, quotedSourceText, translatePublicText } from "../src/lib/publicLocale.ts";

const PUBLIC_ENGLISH_SAMPLES = [
  "项目清单：选择融资设备，待人工复核",
  "交易、生产、营收、负债、流水与合规六维总览",
  "当前设备暂无绑定原始照片；合同金额不可用",
  "材料、证据、事实、置信度和制度结果一一分离",
  "脱敏合成公开演示，不构成自动审批",
  "华南精工丁卯，金额 323.25 万元，状态待补",
];

test("English public surface gate never invents a generic translation for unmapped source text", () => {
  for (const source of PUBLIC_ENGLISH_SAMPLES) {
    const translated = translatePublicText(source, "en");
    assert.match(translated, /^Quoted source text: /);
    assert.doesNotMatch(translated, /source value|unknown/i, translated);
  }
  assert.equal(formatCanonicalText("系统生成·精工甲辰", "en"), "Synthetic Customer 01 · Precision manufacturing");
  assert.equal(quotedSourceText("未建模的原始证据文本", "en"), "Quoted source text: 未建模的原始证据文本");
});

test("English public surface allowlist is limited to the bilingual brand and language choice", () => {
  assert.equal(translatePublicText("signal-council", "en"), "signal-council");
  assert.equal(translatePublicText("中", "en"), "中");
  assert.equal(translatePublicText("项目目录", "zh-CN"), "项目目录");
});
