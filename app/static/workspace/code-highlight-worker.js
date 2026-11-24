"use strict";

importScripts("../vendor/highlight/highlight.min.js");

self.addEventListener("message", ({ data: { side, revision, language, text } }) => {
  const html = self.hljs.getLanguage(language) && !text.split("\n").some((line) => line.length > 1200)
    ? self.hljs.highlight(text, { language, ignoreIllegals: true }).value + "\n"
    : "";
  self.postMessage({ side, revision, html });
});
