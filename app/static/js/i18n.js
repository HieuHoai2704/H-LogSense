(() => {
  // English message -> translation. A translation is a string, or for count-dependent messages an object of
  // CLDR plural categories ({one, few, many, other}) chosen with Intl.PluralRules for the page language.
  const catalog = JSON.parse(document.getElementById("interface-catalog").textContent);
  const language = document.documentElement.lang || "en";
  const pluralRules = new Intl.PluralRules(language);
  const englishRules = new Intl.PluralRules("en");

  const format = (text, values) =>
    text.replace(/\{(\d+)\}/g, (match, index) => (Number(index) < values.length ? String(values[index]) : match));
  const entry = (message) => (Object.hasOwn(catalog, message) ? catalog[message] : undefined);

  window.logsenseTranslate = (message, ...values) => {
    const translated = entry(message);
    if (translated === undefined) return format(message, values);
    return format(typeof translated === "string" ? translated : translated.other, values);
  };

  // tn(count, "{0} item", "{0} items", ...values): the English pair is the key; ``count`` picks the form and is
  // not inserted by itself, so pass the (formatted) number among ``values`` where the text shows it.
  window.logsenseTranslatePlural = (count, singular, plural, ...values) => {
    const number = Number(count);
    const translated = entry(plural);
    let text;
    if (translated === undefined) text = englishRules.select(number) === "one" ? singular : plural;
    else if (typeof translated === "string") text = translated; // the language does not inflect for number
    else text = translated[pluralRules.select(number)] ?? translated.other;
    return format(text, values);
  };

  const form = document.querySelector(".language-picker");
  if (form) {
    form.addEventListener("submit", () => {
      form.elements.next.value = location.pathname + location.search + location.hash;
    });
    form.elements.language.addEventListener("change", () => form.requestSubmit());
  }
})();
