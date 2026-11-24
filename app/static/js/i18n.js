(() => {
  const catalog = JSON.parse(document.getElementById("interface-catalog").textContent);
  window.logsenseTranslate = (message, ...values) => {
    const translated = Object.hasOwn(catalog, message) ? catalog[message] : message;
    return translated.replace(/\{(\d+)\}/g, (match, index) =>
      Number(index) < values.length ? String(values[index]) : match
    );
  };

  const form = document.querySelector(".language-picker");
  if (form) {
    form.addEventListener("submit", () => {
      form.elements.next.value = location.pathname + location.search + location.hash;
    });
    form.elements.language.addEventListener("change", () => form.requestSubmit());
  }
})();
